"""
Valuation Snapshot Module for the Agentic AI Trading System.

Fetches fundamental data (via yfinance) and computes standard valuation
metrics that Fundamental Agents need for bottom-up equity analysis.

Per spec, fundamental agents:
- Value names on the multiples and DCF that actually matter
- Benchmark against peers and their own history
- Goal is variant perception: finding where numbers diverge from consensus

This module provides the raw valuation data. The agent interprets it.

Usage:
    from data_platform.valuations import ValuationService
    vs = ValuationService()
    snap = vs.get_snapshot("XOM")
    peers = vs.peer_comparison("XOM", ["CVX", "COP", "EOG", "SLB"])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValuationSnapshot:
    """Valuation metrics for a single name."""
    ticker: str
    as_of_date: date

    # Price
    current_price: float
    market_cap_mm: float  # millions

    # Multiples
    pe_trailing: Optional[float]
    pe_forward: Optional[float]
    ev_ebitda: Optional[float]
    price_to_book: Optional[float]
    price_to_fcf: Optional[float]
    price_to_sales: Optional[float]
    dividend_yield: Optional[float]

    # Growth & Margins
    revenue_growth_yoy: Optional[float]
    earnings_growth_yoy: Optional[float]
    gross_margin: Optional[float]
    operating_margin: Optional[float]
    net_margin: Optional[float]
    fcf_yield: Optional[float]  # FCF / market cap

    # Balance Sheet
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    roe: Optional[float]

    # Analyst Estimates
    target_price_mean: Optional[float]
    target_price_high: Optional[float]
    target_price_low: Optional[float]
    recommendation: Optional[str]  # "buy", "hold", "sell"
    num_analysts: Optional[int]

    # Earnings
    next_earnings_date: Optional[str]
    earnings_surprise_last: Optional[float]  # % surprise vs consensus


@dataclass(frozen=True)
class PeerComparison:
    """Comparison of a ticker's valuation vs. peers."""
    ticker: str
    peers: list[str]
    as_of_date: date

    # Relative rankings (percentile among peer set, 0-1)
    pe_percentile: Optional[float]       # low = cheap
    ev_ebitda_percentile: Optional[float]
    price_to_fcf_percentile: Optional[float]
    dividend_yield_percentile: Optional[float]  # high = attractive

    # Vs. peer median
    pe_vs_median: Optional[float]        # ratio (0.8 = 20% discount)
    ev_ebitda_vs_median: Optional[float]
    margin_vs_median: Optional[float]    # operating margin difference

    # Simple verdict
    relative_value: str  # "cheap" | "fair" | "expensive"


@dataclass
class RevisionTracker:
    """Tracks earnings estimate revision direction."""
    ticker: str
    current_eps_estimate: Optional[float]
    eps_estimate_30d_ago: Optional[float]
    eps_estimate_90d_ago: Optional[float]
    revision_direction_30d: str  # "up" | "down" | "flat"
    revision_direction_90d: str
    revision_magnitude_30d_pct: Optional[float]


# ---------------------------------------------------------------------------
# Valuation Service
# ---------------------------------------------------------------------------

class ValuationService:
    """
    Fetches and computes valuation metrics using yfinance.

    Note: yfinance provides trailing data and analyst estimates.
    For forward estimates and revision history, a paid source
    (FactSet, IBES) would be needed in production.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def _fetch_info(self, ticker: str) -> dict:
        """Fetch ticker info from yfinance (with simple in-memory cache)."""
        if ticker in self._cache:
            return self._cache[ticker]

        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info or {}
            self._cache[ticker] = info
            return info
        except Exception:
            return {}

    def get_snapshot(self, ticker: str) -> Optional[ValuationSnapshot]:
        """
        Get a full valuation snapshot for a ticker.

        Returns None if the ticker can't be fetched.
        """
        info = self._fetch_info(ticker)
        if not info:
            return None

        def safe_get(key, default=None):
            val = info.get(key, default)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return val

        # Market cap
        market_cap = safe_get("marketCap", 0)
        market_cap_mm = market_cap / 1_000_000 if market_cap else 0

        # FCF yield
        fcf = safe_get("freeCashflow")
        fcf_yield = (fcf / market_cap) if (fcf and market_cap and market_cap > 0) else None

        # Earnings date
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is not None and not cal.empty:
                next_earn = str(cal.iloc[0, 0]) if hasattr(cal, 'iloc') else None
            else:
                next_earn = None
        except Exception:
            next_earn = None

        return ValuationSnapshot(
            ticker=ticker,
            as_of_date=date.today(),
            current_price=safe_get("currentPrice", safe_get("regularMarketPrice", 0)),
            market_cap_mm=round(market_cap_mm, 1),
            pe_trailing=safe_get("trailingPE"),
            pe_forward=safe_get("forwardPE"),
            ev_ebitda=safe_get("enterpriseToEbitda"),
            price_to_book=safe_get("priceToBook"),
            price_to_fcf=None,  # computed below
            price_to_sales=safe_get("priceToSalesTrailing12Months"),
            dividend_yield=safe_get("dividendYield"),
            revenue_growth_yoy=safe_get("revenueGrowth"),
            earnings_growth_yoy=safe_get("earningsGrowth"),
            gross_margin=safe_get("grossMargins"),
            operating_margin=safe_get("operatingMargins"),
            net_margin=safe_get("profitMargins"),
            fcf_yield=round(fcf_yield, 4) if fcf_yield else None,
            debt_to_equity=safe_get("debtToEquity"),
            current_ratio=safe_get("currentRatio"),
            roe=safe_get("returnOnEquity"),
            target_price_mean=safe_get("targetMeanPrice"),
            target_price_high=safe_get("targetHighPrice"),
            target_price_low=safe_get("targetLowPrice"),
            recommendation=safe_get("recommendationKey"),
            num_analysts=safe_get("numberOfAnalystOpinions"),
            next_earnings_date=next_earn,
            earnings_surprise_last=None,  # requires historical earnings data
        )

    def peer_comparison(
        self,
        ticker: str,
        peers: list[str],
    ) -> Optional[PeerComparison]:
        """
        Compare a ticker's valuation metrics against a peer set.

        Args:
            ticker: The name to evaluate.
            peers: List of peer tickers for comparison.

        Returns:
            PeerComparison with relative rankings, or None if insufficient data.
        """
        # Fetch all snapshots
        target_snap = self.get_snapshot(ticker)
        if target_snap is None:
            return None

        peer_snaps = []
        for p in peers:
            snap = self.get_snapshot(p)
            if snap:
                peer_snaps.append(snap)

        if len(peer_snaps) < 2:
            return None

        # All names including target
        all_snaps = [target_snap] + peer_snaps

        # Compute percentiles for target among the group
        def percentile_rank(values: list, target_val):
            """What % of values is the target below (lower = cheaper for multiples)."""
            valid = [v for v in values if v is not None]
            if not valid or target_val is None:
                return None
            below = sum(1 for v in valid if v < target_val)
            return round(below / len(valid), 3)

        def vs_median(values: list, target_val):
            """Target as a ratio of median (0.8 = 20% discount)."""
            valid = [v for v in values if v is not None]
            if not valid or target_val is None:
                return None
            med = float(np.median(valid))
            return round(target_val / med, 3) if med != 0 else None

        pe_vals = [s.pe_forward or s.pe_trailing for s in all_snaps]
        ev_vals = [s.ev_ebitda for s in all_snaps]
        fcf_vals = [s.fcf_yield for s in all_snaps]
        div_vals = [s.dividend_yield for s in all_snaps]
        margin_vals = [s.operating_margin for s in all_snaps]

        target_pe = target_snap.pe_forward or target_snap.pe_trailing
        pe_pctl = percentile_rank(pe_vals, target_pe)
        ev_pctl = percentile_rank(ev_vals, target_snap.ev_ebitda)
        # For dividend yield: higher is better, so invert
        div_pctl = percentile_rank(div_vals, target_snap.dividend_yield)
        if div_pctl is not None:
            div_pctl = round(1.0 - div_pctl, 3)  # flip so high yield = high percentile

        pe_med = vs_median(pe_vals, target_pe)
        ev_med = vs_median(ev_vals, target_snap.ev_ebitda)

        # Margin vs median (difference, not ratio)
        valid_margins = [m for m in margin_vals if m is not None]
        margin_diff = None
        if valid_margins and target_snap.operating_margin is not None:
            med_margin = float(np.median(valid_margins))
            margin_diff = round(target_snap.operating_margin - med_margin, 4)

        # Simple relative value verdict
        if pe_pctl is not None:
            if pe_pctl <= 0.3:
                rel_val = "cheap"
            elif pe_pctl >= 0.7:
                rel_val = "expensive"
            else:
                rel_val = "fair"
        else:
            rel_val = "fair"

        return PeerComparison(
            ticker=ticker,
            peers=peers,
            as_of_date=date.today(),
            pe_percentile=pe_pctl,
            ev_ebitda_percentile=ev_pctl,
            price_to_fcf_percentile=None,  # would need P/FCF for all
            dividend_yield_percentile=div_pctl,
            pe_vs_median=pe_med,
            ev_ebitda_vs_median=ev_med,
            margin_vs_median=margin_diff,
            relative_value=rel_val,
        )

    def revision_tracker(self, ticker: str) -> Optional[RevisionTracker]:
        """
        Track earnings estimate revisions.

        Note: yfinance has limited revision history. In production,
        this would use FactSet/IBES for full revision data.
        For now, we can only flag if current estimate exists.
        """
        info = self._fetch_info(ticker)
        if not info:
            return None

        forward_eps = info.get("forwardEps")

        # yfinance doesn't provide historical estimates, so we can't compute
        # actual 30d/90d revisions without a paid source. We return the
        # structure with what we have.
        return RevisionTracker(
            ticker=ticker,
            current_eps_estimate=forward_eps,
            eps_estimate_30d_ago=None,  # requires paid data
            eps_estimate_90d_ago=None,
            revision_direction_30d="unknown",
            revision_direction_90d="unknown",
            revision_magnitude_30d_pct=None,
        )

    def clear_cache(self) -> None:
        """Clear the in-memory info cache."""
        self._cache.clear()
