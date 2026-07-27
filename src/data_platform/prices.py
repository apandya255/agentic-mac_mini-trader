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

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Default database path — relative to project root
_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "prices.db"


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
                    PRIMARY KEY (ticker, date)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_price_ticker_date 
                ON price_history (ticker, date DESC)
            """)

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    def update(
        self,
        tickers: list[str],
        lookback_days: int = 400,
        progress: bool = False,
    ) -> int:
        """
        Fetch EOD data for given tickers and upsert into the database.
        Only fetches data newer than what's already stored.

        Args:
            tickers: List of ticker symbols to update.
            lookback_days: How far back to fetch if no data exists (default 400 for 252 + buffer).
            progress: If True, print progress updates.

        Returns:
            Number of new rows inserted.
        """
        import yfinance as yf

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
                continue  # Already up to date

            try:
                data = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=(date.today() + timedelta(days=1)).isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
                if data.empty:
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
                    ))

                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany("""
                        INSERT OR REPLACE INTO price_history 
                        (ticker, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, rows)

                total_inserted += len(rows)

            except Exception:
                continue  # Skip failures, don't break the batch

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
