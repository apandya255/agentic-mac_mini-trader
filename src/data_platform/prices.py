"""
Price data service for the Agentic AI Trading System.

Fetches EOD OHLCV data from yfinance, stores in a local SQLite database,
and provides query functions for price history, returns, and pair ratios.

Pair ratio representation matches partner spec:
  "every position is one line at a level (pairs as the ratio, XLE/RSP @ 0.52)"

Usage:
    svc = PriceService()
    svc.update(["XLE", "RSP", "XOM"])       # fetch and store latest data
    df = svc.get_history("XOM", 252)         # last 252 trading days
    ratio = svc.get_pair_ratio("XLE", "RSP") # returns PairRatio dataclass
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.data_platform.market_calendar import is_trading_day

# Lazy/guarded Telegram import to avoid circular dependencies
try:
    from src.telegram_bot import send_message as _send_telegram
except ImportError:
    _send_telegram = None

logger = logging.getLogger(__name__)

# Default database path — relative to project root
_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "prices.db"


# ---------------------------------------------------------------------------
# Alpha Vantage Rate Limiter
# ---------------------------------------------------------------------------


class _AVRateLimiter:
    """Token bucket rate limiter: 5 calls per 60 seconds."""

    def __init__(self, max_calls: int = 5, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: list[float] = []

    def acquire(self) -> None:
        """Block until a call slot is available."""
        now = time.time()
        # Remove calls older than the period
        self._calls = [t for t in self._calls if now - t < self.period]
        if len(self._calls) >= self.max_calls:
            # Wait until the oldest call expires
            sleep_time = self.period - (now - self._calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
            self._calls = self._calls[1:]  # Remove expired
        self._calls.append(time.time())


_av_rate_limiter = _AVRateLimiter()


@dataclass(frozen=True)
class PairRatio:
    """Represents a pair ratio (long_ticker / short_ticker) with context."""
    long_ticker: str
    short_ticker: str
    current_ratio: float
    ratio_52w_high: float
    ratio_52w_low: float
    ratio_z_score: float  # z-score vs. trailing 252-day mean/std
    ratio_percentile: float  # percentile rank in trailing 252 days
    as_of_date: date


class PriceService:
    """
    EOD price data service backed by SQLite.

    Handles fetching from yfinance, local storage, and derived computations
    (returns, pair ratios, relative strength).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.fetch_status: dict[str, str] = {}
        self._init_db()

    def _init_db(self) -> None:
        """Create the price_history table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    source TEXT DEFAULT 'yfinance',
                    PRIMARY KEY (ticker, date)
                )
            """)
            # Migration: add source column if table existed without it
            try:
                conn.execute(
                    "ALTER TABLE price_history ADD COLUMN source TEXT DEFAULT 'yfinance'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_price_ticker_date 
                ON price_history (ticker, date DESC)
            """)

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    def _fetch_with_retry(
        self, ticker: str, start: date, max_retries: int = 3
    ) -> pd.DataFrame | None:
        """
        Fetch price data from yfinance with exponential backoff retry.

        Attempts an initial fetch plus up to max_retries additional attempts.
        On each failure, sleeps 2^(attempt+1) seconds (2, 4, 8s for retries 1-3).

        Args:
            ticker: Ticker symbol to fetch.
            start: Start date for the fetch window.
            max_retries: Maximum number of retry attempts after the initial try.

        Returns:
            DataFrame with OHLCV data, or None if all attempts fail.
        """
        import yfinance as yf

        total_attempts = max_retries + 1  # initial + retries

        for attempt in range(total_attempts):
            try:
                data = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=(date.today() + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=True,
                )

                if data.empty:
                    return data

                # yfinance 1.2+ returns MultiIndex columns even for single ticker
                # Flatten: ('Close', 'XOM') -> 'Close'
                if hasattr(data.columns, 'levels'):
                    data.columns = data.columns.get_level_values(0)

                return data

            except Exception as e:
                if attempt < total_attempts - 1:
                    delay = 2 ** (attempt + 1)
                    logger.warning(
                        "Retry %d/%d for ticker %s after %s: %s (sleeping %ds)",
                        attempt + 1,
                        max_retries,
                        ticker,
                        type(e).__name__,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "All %d attempts exhausted for ticker %s. Last error: %s: %s",
                        total_attempts,
                        ticker,
                        type(e).__name__,
                        str(e),
                    )

        return None

    def get_fetch_status(self, ticker: str) -> str:
        """
        Return the fetch status for a given ticker.

        Returns 'ok', 'fetch_failed', or 'unfetchable'.
        Defaults to 'ok' if the ticker has not been tracked.
        """
        return self.fetch_status.get(ticker, "ok")

    def _fetch_alpha_vantage(self, ticker: str, start_date: date) -> pd.DataFrame | None:
        """
        Fetch price data from Alpha Vantage as a fallback source.

        Uses stdlib urllib (no requests dependency). Respects the module-level
        rate limiter (_av_rate_limiter) to stay within the 5 calls/minute
        free-tier limit.

        Args:
            ticker: Ticker symbol to fetch.
            start_date: Only return data from this date onward.

        Returns:
            DataFrame with columns (Open, High, Low, Close, Volume) matching
            yfinance schema, or None on any error or if API key is not set.
        """
        api_key = os.environ.get("ALPHAVANTAGE_API_KEY", "")
        if not api_key:
            logger.debug("ALPHAVANTAGE_API_KEY not set; skipping Alpha Vantage fallback")
            return None

        _av_rate_limiter.acquire()

        url = (
            f"https://www.alphavantage.co/query?"
            f"function=TIME_SERIES_DAILY&symbol={ticker}"
            f"&outputsize=full&apikey={api_key}"
        )

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")

            payload = json.loads(raw)
            time_series = payload.get("Time Series (Daily)")
            if not time_series:
                logger.warning(
                    "Alpha Vantage returned no 'Time Series (Daily)' for %s: %s",
                    ticker,
                    payload.get("Note") or payload.get("Error Message") or "unknown",
                )
                return None

            records = []
            for date_str, values in time_series.items():
                dt = date.fromisoformat(date_str)
                if dt < start_date:
                    continue
                records.append({
                    "Date": pd.Timestamp(date_str),
                    "Open": float(values["1. open"]),
                    "High": float(values["2. high"]),
                    "Low": float(values["3. low"]),
                    "Close": float(values["4. close"]),
                    "Volume": int(values["5. volume"]),
                })

            if not records:
                logger.info("Alpha Vantage returned no data for %s after %s", ticker, start_date)
                return None

            df = pd.DataFrame(records)
            df = df.set_index("Date").sort_index()
            return df

        except Exception as e:
            logger.error(
                "Alpha Vantage fetch failed for %s: %s: %s",
                ticker,
                type(e).__name__,
                str(e),
            )
            return None

    def update(
        self,
        tickers: list[str],
        lookback_days: int = 400,
        progress: bool = False,
    ) -> int:
        """
        Fetch EOD data for given tickers and upsert into the database.
        Only fetches data newer than what's already stored.

        Uses exponential backoff retry via _fetch_with_retry(). Tracks
        per-ticker fetch outcomes in self.fetch_status.

        Args:
            tickers: List of ticker symbols to update.
            lookback_days: How far back to fetch if no data exists (default 400 for 252 + buffer).
            progress: If True, print progress updates.

        Returns:
            Number of new rows inserted.
        """
        self.fetch_status = {}
        total_inserted = 0

        for i, ticker in enumerate(tickers):
            if progress and (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(tickers)}] Fetching {ticker}...")

            # Determine start date: day after last stored date, or lookback
            last_date = self._get_last_date(ticker)
            if last_date:
                start = last_date + timedelta(days=1)
            else:
                start = date.today() - timedelta(days=lookback_days)

            if start > date.today():
                self.fetch_status[ticker] = "ok"
                continue  # Already up to date

            data = self._fetch_with_retry(ticker, start)

            if data is None:
                # Primary source failed — try Alpha Vantage fallback
                av_data = self._fetch_alpha_vantage(ticker, start)
                if av_data is not None and not av_data.empty:
                    # Process Alpha Vantage data with source tag
                    rows = []
                    for dt, row in av_data.iterrows():
                        rows.append((
                            ticker,
                            dt.strftime("%Y-%m-%d"),
                            float(row["Open"]) if not np.isnan(row["Open"]) else None,
                            float(row["High"]) if not np.isnan(row["High"]) else None,
                            float(row["Low"]) if not np.isnan(row["Low"]) else None,
                            float(row["Close"]) if not np.isnan(row["Close"]) else None,
                            int(row["Volume"]) if not np.isnan(row["Volume"]) else None,
                            "alpha_vantage",
                        ))

                    with sqlite3.connect(self.db_path) as conn:
                        conn.executemany("""
                            INSERT OR REPLACE INTO price_history 
                            (ticker, date, open, high, low, close, volume, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, rows)

                    total_inserted += len(rows)
                    self.fetch_status[ticker] = "ok"
                    continue
                else:
                    # Both yfinance and Alpha Vantage failed
                    self.fetch_status[ticker] = "unfetchable"
                    logger.critical(
                        "Ticker %s unfetchable after yfinance retry + Alpha Vantage fallback",
                        ticker,
                    )
                    if _send_telegram is not None:
                        try:
                            _send_telegram(
                                f"{ticker} unfetchable after yfinance retry "
                                f"+ Alpha Vantage fallback",
                                severity="critical",
                            )
                        except Exception as e:
                            logger.error("Failed to send Telegram alert: %s", e)
                    continue

            if data.empty:
                self.fetch_status[ticker] = "ok"
                continue

            rows = []
            for dt, row in data.iterrows():
                rows.append((
                    ticker,
                    dt.strftime("%Y-%m-%d"),
                    float(row["Open"]) if not np.isnan(row["Open"]) else None,
                    float(row["High"]) if not np.isnan(row["High"]) else None,
                    float(row["Low"]) if not np.isnan(row["Low"]) else None,
                    float(row["Close"]) if not np.isnan(row["Close"]) else None,
                    int(row["Volume"]) if not np.isnan(row["Volume"]) else None,
                    "yfinance",
                ))

            with sqlite3.connect(self.db_path) as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO price_history 
                    (ticker, date, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)

            total_inserted += len(rows)
            self.fetch_status[ticker] = "ok"

        return total_inserted

    def _get_last_date(self, ticker: str) -> Optional[date]:
        """Get the most recent date stored for a ticker."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM price_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            if row and row[0]:
                return date.fromisoformat(row[0])
        return None

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    def backfill_position(self, ticker: str, entry_date: date) -> dict:
        """
        Ensure continuous daily price data from entry_date to today.

        Checks for gaps (expected trading days with no stored data),
        groups consecutive gaps into ranges, and fetches missing data
        via yfinance (with retry) then Alpha Vantage as fallback.

        Args:
            ticker: Ticker symbol to backfill.
            entry_date: The position's entry date (start of required range).

        Returns:
            {"ticker": str, "days_backfilled": int, "gaps_remaining": int}
        """
        today = date.today()

        # 1. Generate expected trading days from entry_date to today
        expected_days: list[date] = []
        current = entry_date
        while current <= today:
            if is_trading_day(current):
                expected_days.append(current)
            current += timedelta(days=1)

        if not expected_days:
            return {"ticker": ticker, "days_backfilled": 0, "gaps_remaining": 0}

        # 2. Query stored dates for this ticker in the range
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT date FROM price_history WHERE ticker = ? AND date >= ? AND date <= ?",
                (ticker, entry_date.isoformat(), today.isoformat()),
            ).fetchall()
        stored_dates: set[date] = {date.fromisoformat(r[0]) for r in rows}

        # 3. Compute gaps
        gap_days = [d for d in expected_days if d not in stored_dates]

        if not gap_days:
            return {"ticker": ticker, "days_backfilled": 0, "gaps_remaining": 0}

        # 5. Group consecutive gaps into date ranges for efficient fetching
        gap_ranges = self._group_consecutive_dates(gap_days)

        # 6. Fetch missing data for each gap range
        days_filled = 0
        gap_days_set = set(gap_days)
        for gap_start, gap_end in gap_ranges:
            source_tag = "yfinance"
            data = self._fetch_with_retry(ticker, gap_start)

            if data is None or data.empty:
                # Fallback to Alpha Vantage
                data = self._fetch_alpha_vantage(ticker, gap_start)
                source_tag = "alpha_vantage"

            if data is not None and not data.empty:
                # Filter to only the gap range dates that are actual gaps
                rows_to_insert = []
                for dt, row in data.iterrows():
                    row_date = dt.date() if hasattr(dt, 'date') else dt
                    if isinstance(row_date, str):
                        row_date = date.fromisoformat(row_date)
                    if gap_start <= row_date <= gap_end and row_date in gap_days_set:
                        rows_to_insert.append((
                            ticker,
                            row_date.isoformat(),
                            float(row["Open"]) if not np.isnan(row["Open"]) else None,
                            float(row["High"]) if not np.isnan(row["High"]) else None,
                            float(row["Low"]) if not np.isnan(row["Low"]) else None,
                            float(row["Close"]) if not np.isnan(row["Close"]) else None,
                            int(row["Volume"]) if not np.isnan(row["Volume"]) else None,
                            source_tag,
                        ))

                if rows_to_insert:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.executemany("""
                            INSERT OR REPLACE INTO price_history
                            (ticker, date, open, high, low, close, volume, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, rows_to_insert)
                    days_filled += len(rows_to_insert)

        # 8. Recount remaining gaps
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT date FROM price_history WHERE ticker = ? AND date >= ? AND date <= ?",
                (ticker, entry_date.isoformat(), today.isoformat()),
            ).fetchall()
        stored_dates_after: set[date] = {date.fromisoformat(r[0]) for r in rows}
        gaps_remaining = len([d for d in expected_days if d not in stored_dates_after])

        # 9. Log
        logger.info(
            "Backfill %s: %d days filled, %d gaps remaining",
            ticker, days_filled, gaps_remaining,
        )

        # 10. Return result
        return {
            "ticker": ticker,
            "days_backfilled": days_filled,
            "gaps_remaining": gaps_remaining,
        }

    @staticmethod
    def _group_consecutive_dates(dates: list[date]) -> list[tuple[date, date]]:
        """
        Group a sorted list of dates into consecutive ranges.

        Returns a list of (start_date, end_date) tuples representing
        consecutive date ranges.
        """
        if not dates:
            return []

        sorted_dates = sorted(dates)
        ranges: list[tuple[date, date]] = []
        range_start = sorted_dates[0]
        prev = sorted_dates[0]

        for d in sorted_dates[1:]:
            # If more than 3 days apart (accounting for weekends), start a new range
            if (d - prev).days > 3:
                ranges.append((range_start, prev))
                range_start = d
            prev = d

        ranges.append((range_start, prev))
        return ranges

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_history(self, ticker: str, lookback_days: int = 252) -> pd.DataFrame:
        """
        Get price history for a ticker from local DB.

        Returns a DataFrame with columns: open, high, low, close, volume
        indexed by date (most recent last).
        """
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                """
                SELECT date, open, high, low, close, volume
                FROM price_history
                WHERE ticker = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                conn,
                params=(ticker, lookback_days),
            )

        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df

    def get_close(self, ticker: str, lookback_days: int = 252) -> pd.Series:
        """Get just the close price series for a ticker."""
        df = self.get_history(ticker, lookback_days)
        if df.empty:
            return pd.Series(dtype=float, name=ticker)
        return df["close"].rename(ticker)

    def get_latest_close(self, ticker: str) -> Optional[float]:
        """Get the most recent close price for a ticker."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT close FROM price_history 
                WHERE ticker = ? AND close IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                (ticker,),
            ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Returns
    # ------------------------------------------------------------------

    def compute_returns(
        self,
        ticker: str,
        periods: list[int] | None = None,
    ) -> dict[str, float]:
        """
        Compute trailing returns for standard periods.

        Args:
            ticker: Ticker symbol.
            periods: List of trading-day lookback periods.
                     Defaults to [1, 5, 21, 63, 126, 252] (1D to 1Y).

        Returns:
            Dict mapping period label to return (e.g., {"1D": 0.012, "1W": -0.005, ...}).
        """
        if periods is None:
            periods = [1, 5, 21, 63, 126, 252]

        labels = {1: "1D", 5: "1W", 21: "1M", 63: "3M", 126: "6M", 252: "1Y"}

        closes = self.get_close(ticker, max(periods) + 5)
        if closes.empty or len(closes) < 2:
            return {}

        results = {}
        current = closes.iloc[-1]
        for p in periods:
            if len(closes) > p:
                prior = closes.iloc[-(p + 1)]
                ret = (current - prior) / prior
                label = labels.get(p, f"{p}D")
                results[label] = round(float(ret), 6)

        return results

    def compute_daily_returns(self, ticker: str, lookback_days: int = 252) -> pd.Series:
        """Compute daily percentage returns for a ticker."""
        closes = self.get_close(ticker, lookback_days + 5)
        if closes.empty or len(closes) < 2:
            return pd.Series(dtype=float, name=ticker)
        return closes.pct_change().dropna().rename(ticker)

    # ------------------------------------------------------------------
    # Pair Ratios
    # ------------------------------------------------------------------

    def get_pair_ratio(
        self,
        long_ticker: str,
        short_ticker: str,
        lookback_days: int = 252,
    ) -> Optional[PairRatio]:
        """
        Compute the pair ratio (long / short) with z-score and percentile.

        This implements the partner's book representation:
        "pairs as the ratio, XLE/RSP @ 0.52"

        Args:
            long_ticker: Numerator ticker (the long leg).
            short_ticker: Denominator ticker (the short/hedge leg).
            lookback_days: Window for z-score and percentile computation.

        Returns:
            PairRatio dataclass, or None if insufficient data.
        """
        long_prices = self.get_close(long_ticker, lookback_days + 5)
        short_prices = self.get_close(short_ticker, lookback_days + 5)

        if long_prices.empty or short_prices.empty:
            return None

        # Align dates
        combined = pd.DataFrame({"long": long_prices, "short": short_prices}).dropna()
        if len(combined) < 20:
            return None

        ratio_series = combined["long"] / combined["short"]
        current_ratio = float(ratio_series.iloc[-1])

        # Stats over the lookback window
        window = ratio_series.iloc[-lookback_days:] if len(ratio_series) >= lookback_days else ratio_series
        mean = float(window.mean())
        std = float(window.std())
        z_score = (current_ratio - mean) / std if std > 0 else 0.0

        # Percentile rank
        percentile = float((window < current_ratio).sum() / len(window))

        # 52-week high/low
        high = float(window.max())
        low = float(window.min())

        as_of = combined.index[-1].date() if hasattr(combined.index[-1], "date") else date.today()

        return PairRatio(
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            current_ratio=round(current_ratio, 4),
            ratio_52w_high=round(high, 4),
            ratio_52w_low=round(low, 4),
            ratio_z_score=round(z_score, 3),
            ratio_percentile=round(percentile, 3),
            as_of_date=as_of,
        )

    # ------------------------------------------------------------------
    # Relative Strength
    # ------------------------------------------------------------------

    def relative_strength(
        self,
        ticker: str,
        benchmark: str = "SPY",
        lookback_days: int = 63,
    ) -> Optional[float]:
        """
        Compute relative strength of ticker vs. benchmark over a period.
        Returns the ratio of ticker return / benchmark return - 1.
        Positive = outperforming, negative = underperforming.
        """
        ticker_closes = self.get_close(ticker, lookback_days + 5)
        bench_closes = self.get_close(benchmark, lookback_days + 5)

        if len(ticker_closes) < lookback_days or len(bench_closes) < lookback_days:
            return None

        ticker_ret = (ticker_closes.iloc[-1] / ticker_closes.iloc[-lookback_days]) - 1
        bench_ret = (bench_closes.iloc[-1] / bench_closes.iloc[-lookback_days]) - 1

        if bench_ret == 0:
            return None

        return round(float(ticker_ret - bench_ret), 4)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def has_data(self, ticker: str) -> bool:
        """Check if we have any stored data for a ticker."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM price_history WHERE ticker = ?",
                (ticker,),
            ).fetchone()
        return row[0] > 0 if row else False

    def data_coverage(self) -> dict[str, int]:
        """Return a dict of ticker -> number of stored rows."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT ticker, COUNT(*) FROM price_history GROUP BY ticker"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    @property
    def db_size_mb(self) -> float:
        """Size of the database file in MB."""
        if self.db_path.exists():
            return self.db_path.stat().st_size / (1024 * 1024)
        return 0.0


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from .universe import Universe

    parser = argparse.ArgumentParser(description="Update price database")
    parser.add_argument("--full", action="store_true", help="Fetch full universe")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to update")
    parser.add_argument("--lookback", type=int, default=400, help="Lookback days for new tickers")
    args = parser.parse_args()

    svc = PriceService()

    if args.tickers:
        tickers = args.tickers
    elif args.full:
        u = Universe()
        u.load()
        tickers = u.all_tickers()
    else:
        # Default: just ETFs and hedges (fast)
        u = Universe()
        tickers = (
            u.sector_etf_tickers
            + u.equal_weight_etf_tickers
            + u.country_etf_tickers
            + u.commodity_tickers
            + u.hedge_tickers
        )

    print(f"Updating {len(tickers)} tickers...")
    inserted = svc.update(tickers, lookback_days=args.lookback, progress=True)
    print(f"Done. {inserted} rows inserted/updated. DB size: {svc.db_size_mb:.1f} MB")
