"""
Tests for src/trading/factor_beta.py

Covers:
- compute_factor_betas returns results when enough data exists
- compute_factor_betas returns empty when insufficient history
- get_alert_level thresholds (None, "warning", "critical")
- load_factors / save_factors round-trip
- OLS math correctness with known values
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.trading.factor_beta import (
    BETA_CRITICAL_THRESHOLD,
    BETA_WARNING_THRESHOLD,
    FactorBetaResult,
    compute_factor_betas,
    get_alert_level,
    load_factors,
    save_factors,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_returns_series(n: int, seed: int = 42, name: str = "TEST") -> pd.Series:
    """Generate a pd.Series of random daily returns with a DatetimeIndex."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=date.today(), periods=n)
    return pd.Series(rng.normal(0.0005, 0.015, n), index=dates, name=name)


def _make_correlated_returns(
    factor_returns: pd.Series, beta: float, noise_std: float = 0.005, seed: int = 99
) -> pd.Series:
    """Generate ticker returns that have an approximate beta to factor_returns."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_std, len(factor_returns))
    ticker_returns = beta * factor_returns.values + noise
    return pd.Series(ticker_returns, index=factor_returns.index, name="TICKER")


# ---------------------------------------------------------------------------
# Tests: compute_factor_betas
# ---------------------------------------------------------------------------


class TestComputeFactorBetas:
    """Tests for compute_factor_betas function."""

    def test_returns_results_when_enough_data(self):
        """When sufficient aligned data exists, returns FactorBetaResult list."""
        factor_returns = _make_returns_series(200, seed=10, name="SPY")
        ticker_returns = _make_correlated_returns(factor_returns, beta=0.8)

        price_service = MagicMock()
        price_service.compute_daily_returns.side_effect = (
            lambda ticker, lookback_days: ticker_returns
            if ticker == "XOM"
            else factor_returns
        )

        results = compute_factor_betas(
            "XOM", price_service, {"market": "SPY"}, min_days=126
        )

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, FactorBetaResult)
        assert result.ticker == "XOM"
        assert result.factor_name == "market"
        assert result.trading_days_used == 200
        assert result.computed_date == date.today().isoformat()
        # Beta should be close to 0.8 (not exact due to noise)
        assert 0.5 < result.beta < 1.1

    def test_returns_empty_when_ticker_has_insufficient_history(self):
        """When the ticker has fewer than min_days of returns, returns empty list."""
        # Only 50 days of data — below min_days=126
        short_returns = _make_returns_series(50, seed=1, name="SHORT")

        price_service = MagicMock()
        price_service.compute_daily_returns.return_value = short_returns

        results = compute_factor_betas(
            "SHORT", price_service, {"market": "SPY"}, min_days=126
        )

        assert results == []

    def test_skips_factor_with_insufficient_aligned_data(self):
        """When aligned data < min_days for a factor, that factor is skipped."""
        # Ticker has plenty of data
        ticker_returns = _make_returns_series(200, seed=1, name="XOM")
        # Factor has only 50 days — non-overlapping dates
        factor_dates = pd.bdate_range(start="2020-01-01", periods=50)
        factor_returns = pd.Series(
            np.random.default_rng(2).normal(0, 0.01, 50),
            index=factor_dates,
            name="SPY",
        )

        price_service = MagicMock()
        price_service.compute_daily_returns.side_effect = (
            lambda ticker, lookback_days: ticker_returns
            if ticker == "XOM"
            else factor_returns
        )

        results = compute_factor_betas(
            "XOM", price_service, {"market": "SPY"}, min_days=126
        )

        # Factor skipped because alignment yields 0 common dates
        assert results == []

    def test_multiple_factors(self):
        """Computes betas against multiple factors."""
        factor1 = _make_returns_series(200, seed=10, name="SPY")
        factor2 = _make_returns_series(200, seed=20, name="XLE")
        ticker_returns = _make_correlated_returns(factor1, beta=0.5, seed=30)

        def mock_returns(ticker, lookback_days):
            if ticker == "XOM":
                return ticker_returns
            elif ticker == "SPY":
                return factor1
            elif ticker == "XLE":
                return factor2
            return pd.Series(dtype=float)

        price_service = MagicMock()
        price_service.compute_daily_returns.side_effect = mock_returns

        results = compute_factor_betas(
            "XOM", price_service, {"market": "SPY", "energy": "XLE"}, min_days=126
        )

        assert len(results) == 2
        assert results[0].factor_name == "market"
        assert results[1].factor_name == "energy"


# ---------------------------------------------------------------------------
# Tests: OLS math correctness
# ---------------------------------------------------------------------------


class TestOLSCorrectness:
    """Verify OLS regression produces correct beta and R-squared."""

    def test_perfect_correlation_beta_one(self):
        """When ticker = factor (perfect correlation), beta should be ~1.0."""
        returns = _make_returns_series(200, seed=42, name="SPY")

        price_service = MagicMock()
        # Same returns for both — should give beta ≈ 1.0
        price_service.compute_daily_returns.return_value = returns

        results = compute_factor_betas(
            "SPY_CLONE", price_service, {"market": "SPY"}, min_days=126
        )

        assert len(results) == 1
        assert abs(results[0].beta - 1.0) < 0.001
        assert results[0].r_squared > 0.999

    def test_known_beta(self):
        """When ticker returns = 2 * factor returns, beta should be ~2.0."""
        factor_returns = _make_returns_series(200, seed=42, name="SPY")
        # ticker = 2 * factor (no noise)
        ticker_returns = pd.Series(
            factor_returns.values * 2.0, index=factor_returns.index, name="HIGH_BETA"
        )

        def mock_returns(ticker, lookback_days):
            if ticker == "HIGH_BETA":
                return ticker_returns
            return factor_returns

        price_service = MagicMock()
        price_service.compute_daily_returns.side_effect = mock_returns

        results = compute_factor_betas(
            "HIGH_BETA", price_service, {"market": "SPY"}, min_days=126
        )

        assert len(results) == 1
        assert abs(results[0].beta - 2.0) < 0.001
        assert results[0].r_squared > 0.999

    def test_zero_beta_uncorrelated(self):
        """When ticker and factor are uncorrelated, beta should be near 0."""
        # Use independent random series
        factor_returns = _make_returns_series(200, seed=42, name="SPY")
        ticker_returns = _make_returns_series(200, seed=999, name="INDEP")

        def mock_returns(ticker, lookback_days):
            if ticker == "INDEP":
                return ticker_returns
            return factor_returns

        price_service = MagicMock()
        price_service.compute_daily_returns.side_effect = mock_returns

        results = compute_factor_betas(
            "INDEP", price_service, {"market": "SPY"}, min_days=126
        )

        assert len(results) == 1
        # Beta should be near 0 for uncorrelated series (some noise expected)
        assert abs(results[0].beta) < 0.3


# ---------------------------------------------------------------------------
# Tests: get_alert_level
# ---------------------------------------------------------------------------


class TestGetAlertLevel:
    """Tests for alert threshold logic."""

    def test_none_below_warning(self):
        """No alert for |beta| <= 0.4."""
        assert get_alert_level(0.0) is None
        assert get_alert_level(0.2) is None
        assert get_alert_level(0.4) is None
        assert get_alert_level(-0.4) is None
        assert get_alert_level(-0.3) is None

    def test_warning_above_04(self):
        """|beta| > 0.4 but <= 0.6 → warning."""
        assert get_alert_level(0.41) == "warning"
        assert get_alert_level(0.5) == "warning"
        assert get_alert_level(0.6) == "warning"
        assert get_alert_level(-0.41) == "warning"
        assert get_alert_level(-0.5) == "warning"
        assert get_alert_level(-0.6) == "warning"

    def test_critical_above_06(self):
        """|beta| > 0.6 → critical."""
        assert get_alert_level(0.61) == "critical"
        assert get_alert_level(0.8) == "critical"
        assert get_alert_level(1.0) == "critical"
        assert get_alert_level(-0.61) == "critical"
        assert get_alert_level(-0.9) == "critical"


# ---------------------------------------------------------------------------
# Tests: load_factors / save_factors round-trip
# ---------------------------------------------------------------------------


class TestLoadSaveFactors:
    """Tests for JSON persistence of factor beta results."""

    def test_round_trip(self, tmp_path, monkeypatch):
        """save_factors then load_factors returns same data."""
        factors_file = tmp_path / "factors.json"
        monkeypatch.setattr(
            "src.trading.factor_beta.FACTORS_PATH", factors_file
        )

        data = {
            "XOM": {
                "market": {
                    "beta": 0.45,
                    "r_squared": 0.62,
                    "days_used": 252,
                    "computed": "2025-07-15",
                }
            }
        }

        save_factors(data)
        loaded = load_factors()
        assert loaded == data

    def test_load_missing_file(self, tmp_path, monkeypatch):
        """load_factors returns empty dict when file doesn't exist."""
        factors_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr(
            "src.trading.factor_beta.FACTORS_PATH", factors_file
        )

        result = load_factors()
        assert result == {}

    def test_load_corrupt_file(self, tmp_path, monkeypatch):
        """load_factors returns empty dict on corrupt JSON."""
        factors_file = tmp_path / "factors.json"
        factors_file.write_text("not valid json {{{")
        monkeypatch.setattr(
            "src.trading.factor_beta.FACTORS_PATH", factors_file
        )

        result = load_factors()
        assert result == {}

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        """save_factors creates parent directories if needed."""
        factors_file = tmp_path / "deep" / "nested" / "factors.json"
        monkeypatch.setattr(
            "src.trading.factor_beta.FACTORS_PATH", factors_file
        )

        save_factors({"test": "data"})
        assert factors_file.exists()
        assert json.loads(factors_file.read_text()) == {"test": "data"}
