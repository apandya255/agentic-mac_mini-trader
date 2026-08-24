"""
Factor beta computation module.

Computes OLS regression of position daily returns against factor series.
Stores results in memos/state/factors.json. Surfaces alerts when betas
exceed warning (0.4) or critical (0.6) thresholds.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from src.data_platform.prices import PriceService

logger = logging.getLogger(__name__)

FACTORS_PATH = Path(__file__).parent.parent.parent / "memos" / "state" / "factors.json"

BETA_WARNING_THRESHOLD = 0.4
BETA_CRITICAL_THRESHOLD = 0.6


@dataclass
class FactorBetaResult:
    """Result of factor beta computation for a single ticker-factor pair."""

    ticker: str
    factor_name: str
    beta: float
    r_squared: float
    trading_days_used: int
    computed_date: str


def compute_factor_betas(
    ticker: str,
    price_service,  # PriceService instance
    factor_tickers: dict[str, str],  # {"market": "SPY", "energy": "XLE", ...}
    min_days: int = 126,
) -> list[FactorBetaResult]:
    """
    Compute betas for one ticker against all configured factors.

    Uses OLS regression (numpy only) of the ticker's daily returns against
    each factor's daily returns over the last 252 trading days.

    Returns empty list if fewer than min_days of aligned data available.
    """
    results: list[FactorBetaResult] = []

    # Get ticker returns (~252 days = 1 year, request extra for alignment)
    ticker_returns = price_service.compute_daily_returns(ticker, lookback_days=260)
    if len(ticker_returns) < min_days:
        logger.info(
            "insufficient_history: %s has %d days (need %d)",
            ticker,
            len(ticker_returns),
            min_days,
        )
        return results

    for factor_name, factor_ticker in factor_tickers.items():
        factor_returns = price_service.compute_daily_returns(
            factor_ticker, lookback_days=260
        )

        # Align on common dates
        aligned = pd.concat(
            [ticker_returns, factor_returns], axis=1, join="inner"
        ).dropna()

        if len(aligned) < min_days:
            logger.info(
                "insufficient_history: %s vs %s has %d aligned days (need %d)",
                ticker,
                factor_ticker,
                len(aligned),
                min_days,
            )
            continue

        y = aligned.iloc[:, 0].values  # ticker returns
        x = aligned.iloc[:, 1].values  # factor returns

        # OLS: y = alpha + beta * x + epsilon
        # Use numpy lstsq with intercept column
        X = np.column_stack([np.ones(len(x)), x])
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        beta = coeffs[1]

        # R-squared
        y_pred = X @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        results.append(
            FactorBetaResult(
                ticker=ticker,
                factor_name=factor_name,
                beta=round(float(beta), 4),
                r_squared=round(float(r_squared), 4),
                trading_days_used=len(aligned),
                computed_date=date.today().isoformat(),
            )
        )

    return results


def get_alert_level(beta: float) -> str | None:
    """
    Return alert level based on absolute beta value.

    Returns:
        "critical" if |beta| > 0.6
        "warning" if |beta| > 0.4
        None otherwise
    """
    abs_beta = abs(beta)
    if abs_beta > BETA_CRITICAL_THRESHOLD:
        return "critical"
    elif abs_beta > BETA_WARNING_THRESHOLD:
        return "warning"
    return None


def load_factors() -> dict:
    """Load memos/state/factors.json. Returns empty dict on missing/corrupt file."""
    if not FACTORS_PATH.exists():
        return {}
    try:
        return json.loads(FACTORS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_factors(factors: dict) -> None:
    """Save memos/state/factors.json atomically (write to .tmp, then rename)."""
    FACTORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = FACTORS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(factors, indent=2))
    tmp_path.replace(FACTORS_PATH)
