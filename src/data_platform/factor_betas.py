"""
Factor Beta Calculator for the Agentic AI Trading System.

Per spec:
- The book tracks 12-month factor betas to: DXY, SPX, USGG10Yr, VIX,
  Growth/Value, CL1, Large/Small cap, CDX HY 5Y, and XAU.
- The combined book should never run a factor beta beyond ±0.6 to any
  individual factor.
- Computation: rolling 12-month (252 trading day) univariate OLS regression
  of daily book returns vs. each factor's daily returns.

This module:
1. Defines factor proxies (tradeable ETFs/indices that represent each factor)
2. Computes rolling betas for a portfolio return series
3. Checks limits and generates warnings/breaches
4. Computes pairwise correlation matrix for active positions

Usage:
    calc = FactorBetaCalculator(price_service=svc)
    betas = calc.compute_betas(book_daily_returns)
    violations = calc.check_limits(betas)
    corr = calc.correlation_matrix(["XOM", "CVX", "XLE", "EWZ"], window=60)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Factor Definitions — Proxies
# ---------------------------------------------------------------------------

# Each factor is mapped to a tradeable ETF/index that proxies its return.
# These are what we fetch price data for and regress against.

FACTOR_PROXIES: dict[str, dict[str, str]] = {
    "DXY": {
        "description": "US Dollar Index",
        "proxy_ticker": "UUP",  # Invesco DB US Dollar Index Bullish Fund
        "proxy_type": "etf",
    },
    "SPX": {
        "description": "S&P 500",
        "proxy_ticker": "SPY",
        "proxy_type": "etf",
    },
    "USGG10Yr": {
        "description": "US 10-Year Treasury Yield (inverse price proxy)",
        "proxy_ticker": "IEF",  # 7-10 Year Treasury Bond ETF
        "proxy_type": "inverse_etf",  # rising yields = falling IEF
    },
    "VIX": {
        "description": "CBOE Volatility Index",
        "proxy_ticker": "VIXY",  # ProShares VIX Short-Term Futures
        "proxy_type": "etf",
    },
    "Growth_Value": {
        "description": "Growth vs. Value factor (long growth / short value)",
        "proxy_ticker_long": "IWF",  # Russell 1000 Growth
        "proxy_ticker_short": "IWD",  # Russell 1000 Value
        "proxy_type": "ratio",
    },
    "CL1": {
        "description": "WTI Crude Oil Front Month",
        "proxy_ticker": "USO",
        "proxy_type": "etf",
    },
    "Large_Small": {
        "description": "Large Cap vs. Small Cap factor",
        "proxy_ticker_long": "IWB",  # Russell 1000 (large)
        "proxy_ticker_short": "IWM",  # Russell 2000 (small)
        "proxy_type": "ratio",
    },
    "CDX_HY_5Y": {
        "description": "High Yield Credit Spread (inverse HY bond price)",
        "proxy_ticker": "HYG",  # iShares iBoxx HY Corporate Bond
        "proxy_type": "inverse_etf",  # widening spreads = falling HYG
    },
    "XAU": {
        "description": "Gold Spot Price",
        "proxy_ticker": "GLD",
        "proxy_type": "etf",
    },
}

# All tickers needed for factor computation (for price fetching)
FACTOR_PROXY_TICKERS: list[str] = []
for _f, _info in FACTOR_PROXIES.items():
    if "proxy_ticker" in _info:
        FACTOR_PROXY_TICKERS.append(_info["proxy_ticker"])
    if "proxy_ticker_long" in _info:
        FACTOR_PROXY_TICKERS.append(_info["proxy_ticker_long"])
        FACTOR_PROXY_TICKERS.append(_info["proxy_ticker_short"])
FACTOR_PROXY_TICKERS = sorted(set(FACTOR_PROXY_TICKERS))


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FactorBetaResult:
    """Result of factor beta computation for the book."""
    factor: str
    beta: float
    t_stat: float  # statistical significance
    r_squared: float
    status: str  # "ok" | "warning" | "breach"


@dataclass(frozen=True)
class BetaViolation:
    """A factor beta limit violation or warning."""
    factor: str
    beta: float
    limit: float
    severity: str  # "warning" (approaching) | "breach" (exceeded)
    message: str


# ---------------------------------------------------------------------------
# Factor Beta Calculator
# ---------------------------------------------------------------------------

class FactorBetaCalculator:
    """
    Computes rolling factor betas and checks portfolio limits.

    Requires a PriceService instance for fetching factor proxy returns,
    or accepts pre-computed return DataFrames.
    """

    # Hard limit per spec
    BETA_LIMIT: float = 0.6
    # Warning threshold (approaching limit)
    BETA_WARNING: float = 0.5

    def __init__(self, price_service=None):
        """
        Args:
            price_service: Optional PriceService instance for fetching returns.
                           If None, caller must pass factor returns directly.
        """
        self.price_service = price_service

    def get_factor_returns(self, window: int = 280) -> pd.DataFrame:
        """
        Fetch daily returns for all factor proxies.

        Returns a DataFrame with columns = factor names, indexed by date.
        Requires self.price_service to be set.
        """
        if self.price_service is None:
            raise ValueError("price_service required for get_factor_returns()")

        factor_returns = {}

        for factor_name, info in FACTOR_PROXIES.items():
            proxy_type = info["proxy_type"]

            if proxy_type == "ratio":
                # Factor is a ratio of two ETFs (long / short)
                long_rets = self.price_service.compute_daily_returns(
                    info["proxy_ticker_long"], window
                )
                short_rets = self.price_service.compute_daily_returns(
                    info["proxy_ticker_short"], window
                )
                if long_rets.empty or short_rets.empty:
                    continue
                # Ratio return ≈ long return - short return
                combined = pd.DataFrame({"l": long_rets, "s": short_rets}).dropna()
                factor_returns[factor_name] = combined["l"] - combined["s"]

            elif proxy_type == "inverse_etf":
                # Factor moves opposite to the ETF (e.g., rising yields = falling IEF)
                rets = self.price_service.compute_daily_returns(
                    info["proxy_ticker"], window
                )
                if rets.empty:
                    continue
                factor_returns[factor_name] = -rets  # invert

            else:
                # Direct ETF proxy
                rets = self.price_service.compute_daily_returns(
                    info["proxy_ticker"], window
                )
                if rets.empty:
                    continue
                factor_returns[factor_name] = rets

        return pd.DataFrame(factor_returns).dropna()

    def compute_betas(
        self,
        book_returns: pd.Series,
        factor_returns: Optional[pd.DataFrame] = None,
        window: int = 252,
    ) -> list[FactorBetaResult]:
        """
        Compute univariate factor betas for the book.

        For each factor f:
            beta_f = Cov(R_book, R_f) / Var(R_f)

        Using trailing `window` trading days.

        Args:
            book_returns: Daily return series for the book (indexed by date).
            factor_returns: DataFrame of factor returns (columns = factor names).
                            If None, fetches from price_service.
            window: Rolling window in trading days (default 252 = 12 months).

        Returns:
            List of FactorBetaResult for each factor.
        """
        if factor_returns is None:
            factor_returns = self.get_factor_returns(window + 30)

        results = []

        for factor_name in factor_returns.columns:
            # Align book returns with factor returns
            combined = pd.DataFrame({
                "book": book_returns,
                "factor": factor_returns[factor_name],
            }).dropna()

            # Use trailing window
            if len(combined) > window:
                combined = combined.iloc[-window:]

            if len(combined) < 30:
                # Insufficient data
                results.append(FactorBetaResult(
                    factor=factor_name, beta=0.0, t_stat=0.0,
                    r_squared=0.0, status="insufficient_data",
                ))
                continue

            # Univariate OLS: R_book = alpha + beta * R_factor + epsilon
            x = combined["factor"].values
            y = combined["book"].values

            cov = np.cov(y, x)[0, 1]
            var = np.var(x, ddof=1)

            if var == 0:
                beta = 0.0
            else:
                beta = cov / var

            # Compute t-stat and R²
            n = len(combined)
            y_pred = beta * x + (np.mean(y) - beta * np.mean(x))
            residuals = y - y_pred
            sse = np.sum(residuals ** 2)
            sst = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1.0 - (sse / sst) if sst > 0 else 0.0

            se_beta = np.sqrt(sse / (n - 2) / (np.sum((x - np.mean(x)) ** 2))) if n > 2 else 0.0
            t_stat = beta / se_beta if se_beta > 0 else 0.0

            # Determine status
            if abs(beta) > self.BETA_LIMIT:
                status = "breach"
            elif abs(beta) > self.BETA_WARNING:
                status = "warning"
            else:
                status = "ok"

            results.append(FactorBetaResult(
                factor=factor_name,
                beta=round(beta, 4),
                t_stat=round(t_stat, 2),
                r_squared=round(r_squared, 4),
                status=status,
            ))

        return results

    def check_limits(
        self,
        betas: list[FactorBetaResult],
        limit: float = 0.6,
        warning: float = 0.5,
    ) -> list[BetaViolation]:
        """
        Check factor betas against limits and return any violations.

        Args:
            betas: List of FactorBetaResult from compute_betas().
            limit: Hard limit (default ±0.6).
            warning: Warning threshold (default ±0.5).

        Returns:
            List of BetaViolation (empty if all within limits).
        """
        violations = []

        for result in betas:
            if result.status == "insufficient_data":
                continue

            abs_beta = abs(result.beta)

            if abs_beta > limit:
                violations.append(BetaViolation(
                    factor=result.factor,
                    beta=result.beta,
                    limit=limit,
                    severity="breach",
                    message=(
                        f"BREACH: {result.factor} beta = {result.beta:+.3f} "
                        f"(limit ±{limit}). Immediate deleverage required."
                    ),
                ))
            elif abs_beta > warning:
                violations.append(BetaViolation(
                    factor=result.factor,
                    beta=result.beta,
                    limit=limit,
                    severity="warning",
                    message=(
                        f"WARNING: {result.factor} beta = {result.beta:+.3f} "
                        f"(approaching ±{limit} limit). Monitor closely."
                    ),
                ))

        return violations

    # ------------------------------------------------------------------
    # Projected Betas (What-If Analysis)
    # ------------------------------------------------------------------

    def project_beta_impact(
        self,
        current_betas: list[FactorBetaResult],
        new_position_returns: pd.Series,
        new_position_weight: float,
        factor_returns: Optional[pd.DataFrame] = None,
        window: int = 252,
    ) -> list[FactorBetaResult]:
        """
        Project what factor betas would look like after adding a new position.

        This is a simplified projection: assumes the new position's beta
        contribution is additive at its weight.

        Args:
            current_betas: Current book factor betas.
            new_position_returns: Daily returns of the proposed new position.
            new_position_weight: Weight of new position as fraction of NAV.
            factor_returns: Factor return DataFrame.
            window: Regression window.

        Returns:
            Projected FactorBetaResult list after adding the position.
        """
        if factor_returns is None:
            factor_returns = self.get_factor_returns(window + 30)

        # Compute betas of the new position alone
        position_betas = self.compute_betas(
            new_position_returns, factor_returns, window
        )

        # Project: new_book_beta ≈ current_beta + position_weight * position_beta
        # (This is a first-order approximation)
        current_beta_map = {b.factor: b.beta for b in current_betas}
        projected = []

        for pb in position_betas:
            current = current_beta_map.get(pb.factor, 0.0)
            proj_beta = current + new_position_weight * pb.beta

            if abs(proj_beta) > self.BETA_LIMIT:
                status = "breach"
            elif abs(proj_beta) > self.BETA_WARNING:
                status = "warning"
            else:
                status = "ok"

            projected.append(FactorBetaResult(
                factor=pb.factor,
                beta=round(proj_beta, 4),
                t_stat=pb.t_stat,
                r_squared=pb.r_squared,
                status=status,
            ))

        return projected

    # ------------------------------------------------------------------
    # Correlation Matrix
    # ------------------------------------------------------------------

    def correlation_matrix(
        self,
        tickers: list[str],
        window: int = 60,
    ) -> Optional[pd.DataFrame]:
        """
        Compute rolling pairwise correlation matrix for active positions.

        Args:
            tickers: List of position tickers.
            window: Rolling window in trading days (default 60).

        Returns:
            DataFrame correlation matrix (tickers × tickers), or None if
            insufficient data.
        """
        if self.price_service is None:
            raise ValueError("price_service required for correlation_matrix()")

        returns_dict = {}
        for ticker in tickers:
            rets = self.price_service.compute_daily_returns(ticker, window + 10)
            if not rets.empty:
                returns_dict[ticker] = rets

        if len(returns_dict) < 2:
            return None

        returns_df = pd.DataFrame(returns_dict).dropna()

        if len(returns_df) < window:
            # Use whatever data we have
            return returns_df.corr()

        # Use trailing window
        return returns_df.iloc[-window:].corr()

    def crowding_check(
        self,
        tickers: list[str],
        window: int = 60,
        cluster_threshold: float = 0.6,
        book_threshold: float = 0.4,
    ) -> dict:
        """
        Check for correlation crowding per spec:
        - If any cluster of 3+ positions has avg pairwise correlation > 0.6: "crowded"
        - If overall book avg pairwise correlation > 0.4: deleverage alert

        Returns dict with crowded_clusters, avg_pairwise_correlation, and alerts.
        """
        corr = self.correlation_matrix(tickers, window)
        if corr is None or corr.empty:
            return {"crowded_clusters": [], "avg_pairwise_corr": 0.0, "alerts": []}

        n = len(corr)
        # Average pairwise (excluding diagonal)
        mask = np.ones((n, n), dtype=bool)
        np.fill_diagonal(mask, False)
        avg_pairwise = float(corr.values[mask].mean())

        alerts = []
        if avg_pairwise > book_threshold:
            alerts.append(
                f"DELEVERAGE ALERT: Book avg pairwise correlation = {avg_pairwise:.3f} "
                f"(threshold {book_threshold})"
            )

        # Find crowded clusters (simplified: any pair above threshold)
        crowded_pairs = []
        tickers_list = list(corr.columns)
        for i in range(n):
            for j in range(i + 1, n):
                if corr.iloc[i, j] > cluster_threshold:
                    crowded_pairs.append((tickers_list[i], tickers_list[j], round(corr.iloc[i, j], 3)))

        return {
            "crowded_clusters": crowded_pairs,
            "avg_pairwise_corr": round(avg_pairwise, 4),
            "alerts": alerts,
        }
