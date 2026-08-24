"""
Unit tests for Alpha Vantage fallback in PriceService.

Tests the _fetch_alpha_vantage method, _AVRateLimiter, and the
wiring in update() that calls AV after yfinance retries are exhausted.

Requirements: 2.1, 2.2, 2.3, 2.4
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data_platform.prices import PriceService, _AVRateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path for testing."""
    return tmp_path / "test_prices.db"


@pytest.fixture
def svc(tmp_db):
    """Create a PriceService with a temporary database."""
    return PriceService(db_path=tmp_db)


# ---------------------------------------------------------------------------
# _AVRateLimiter Tests
# ---------------------------------------------------------------------------


class TestAVRateLimiter:
    """Tests for the Alpha Vantage rate limiter."""

    def test_allows_up_to_max_calls(self):
        """Within the limit, acquire() should not block."""
        limiter = _AVRateLimiter(max_calls=5, period=60.0)
        start = time.time()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.time() - start
        # All 5 calls should complete near-instantly
        assert elapsed < 1.0

    def test_blocks_on_sixth_call(self):
        """The 6th call within the period should block."""
        limiter = _AVRateLimiter(max_calls=5, period=2.0)
        for _ in range(5):
            limiter.acquire()
        start = time.time()
        limiter.acquire()  # This should block until the period expires
        elapsed = time.time() - start
        # Should have waited roughly the period (2s) minus elapsed time
        assert elapsed >= 1.0  # At least some meaningful wait

    def test_expired_calls_are_removed(self):
        """Calls older than the period should be pruned."""
        limiter = _AVRateLimiter(max_calls=2, period=0.1)
        limiter.acquire()
        limiter.acquire()
        # Wait for the period to expire
        time.sleep(0.15)
        # Should be able to acquire again without blocking
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start
        assert elapsed < 0.1


# ---------------------------------------------------------------------------
# _fetch_alpha_vantage Tests
# ---------------------------------------------------------------------------


class TestFetchAlphaVantage:
    """Tests for the _fetch_alpha_vantage method."""

    def test_returns_none_if_no_api_key(self, svc):
        """Should return None immediately if ALPHAVANTAGE_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = svc._fetch_alpha_vantage("AAPL", date(2024, 1, 1))
        assert result is None

    def test_returns_dataframe_on_success(self, svc):
        """Should parse Alpha Vantage response into DataFrame matching yfinance schema."""
        fake_response = {
            "Meta Data": {"2. Symbol": "AAPL"},
            "Time Series (Daily)": {
                "2024-06-03": {
                    "1. open": "190.50",
                    "2. high": "192.00",
                    "3. low": "189.80",
                    "4. close": "191.20",
                    "5. volume": "55000000",
                },
                "2024-06-04": {
                    "1. open": "191.20",
                    "2. high": "193.50",
                    "3. low": "190.90",
                    "4. close": "193.00",
                    "5. volume": "60000000",
                },
                "2024-01-02": {
                    "1. open": "185.00",
                    "2. high": "186.00",
                    "3. low": "184.50",
                    "4. close": "185.50",
                    "5. volume": "45000000",
                },
            },
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *a: None

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"}):
            with patch("urllib.request.urlopen", return_value=mock_response):
                with patch("src.data_platform.prices._av_rate_limiter"):
                    result = svc._fetch_alpha_vantage("AAPL", date(2024, 6, 1))

        assert result is not None
        assert isinstance(result, pd.DataFrame)
        # Should only include dates >= start_date (2024-06-01)
        assert len(result) == 2
        assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Check values
        assert result.iloc[0]["Open"] == 190.50
        assert result.iloc[1]["Close"] == 193.00

    def test_filters_dates_before_start_date(self, svc):
        """Should not include dates before start_date."""
        fake_response = {
            "Time Series (Daily)": {
                "2024-06-03": {
                    "1. open": "190.50",
                    "2. high": "192.00",
                    "3. low": "189.80",
                    "4. close": "191.20",
                    "5. volume": "55000000",
                },
                "2024-05-30": {
                    "1. open": "188.00",
                    "2. high": "189.00",
                    "3. low": "187.00",
                    "4. close": "188.50",
                    "5. volume": "40000000",
                },
            },
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *a: None

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"}):
            with patch("urllib.request.urlopen", return_value=mock_response):
                with patch("src.data_platform.prices._av_rate_limiter"):
                    result = svc._fetch_alpha_vantage("AAPL", date(2024, 6, 1))

        assert result is not None
        assert len(result) == 1

    def test_returns_none_on_network_error(self, svc):
        """Should return None and log error on network failure."""
        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"}):
            with patch("urllib.request.urlopen", side_effect=Exception("Connection timeout")):
                with patch("src.data_platform.prices._av_rate_limiter"):
                    result = svc._fetch_alpha_vantage("AAPL", date(2024, 6, 1))

        assert result is None

    def test_returns_none_on_missing_time_series_key(self, svc):
        """Should return None when response has no 'Time Series (Daily)' key."""
        fake_response = {"Error Message": "Invalid API call"}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *a: None

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test_key"}):
            with patch("urllib.request.urlopen", return_value=mock_response):
                with patch("src.data_platform.prices._av_rate_limiter"):
                    result = svc._fetch_alpha_vantage("AAPL", date(2024, 6, 1))

        assert result is None


# ---------------------------------------------------------------------------
# update() Wiring Tests — AV Fallback
# ---------------------------------------------------------------------------


class TestUpdateAlphaVantageFallback:
    """Tests for the AV fallback path within update()."""

    def test_calls_av_fallback_when_yf_returns_none(self, svc):
        """When _fetch_with_retry returns None, should try Alpha Vantage."""
        av_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000000],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2024-06-03")], name="Date"),
        )

        with patch.object(svc, "_fetch_with_retry", return_value=None):
            with patch.object(svc, "_fetch_alpha_vantage", return_value=av_df) as mock_av:
                result = svc.update(["AAPL"])

        mock_av.assert_called_once()
        assert result == 1
        assert svc.fetch_status["AAPL"] == "ok"

        # Verify the data was stored with source="alpha_vantage"
        with sqlite3.connect(svc.db_path) as conn:
            row = conn.execute(
                "SELECT source FROM price_history WHERE ticker = 'AAPL'"
            ).fetchone()
        assert row[0] == "alpha_vantage"

    def test_marks_unfetchable_when_both_fail(self, svc):
        """When both yfinance and AV fail, should mark ticker unfetchable."""
        with patch.object(svc, "_fetch_with_retry", return_value=None):
            with patch.object(svc, "_fetch_alpha_vantage", return_value=None):
                with patch("src.data_platform.prices._send_telegram") as mock_tg:
                    result = svc.update(["AAPL"])

        assert result == 0
        assert svc.fetch_status["AAPL"] == "unfetchable"

    def test_sends_telegram_alert_when_unfetchable(self, svc):
        """Should send a critical Telegram alert when ticker is unfetchable."""
        with patch.object(svc, "_fetch_with_retry", return_value=None):
            with patch.object(svc, "_fetch_alpha_vantage", return_value=None):
                with patch("src.data_platform.prices._send_telegram") as mock_tg:
                    svc.update(["XOM"])

        if mock_tg is not None:
            mock_tg.assert_called_once()
            call_args = mock_tg.call_args[0][0]
            assert "XOM" in call_args
            assert "unfetchable" in call_args
            # Severity is passed as a keyword argument (prefix applied by send_message)
            call_kwargs = mock_tg.call_args[1]
            assert call_kwargs.get("severity") == "critical"

    def test_does_not_call_av_when_yf_succeeds(self, svc):
        """When _fetch_with_retry returns data, should not call AV."""
        yf_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [101.0],
                "Low": [99.0],
                "Close": [100.5],
                "Volume": [1000000],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2024-06-03")], name="Date"),
        )

        with patch.object(svc, "_fetch_with_retry", return_value=yf_df):
            with patch.object(svc, "_fetch_alpha_vantage") as mock_av:
                svc.update(["AAPL"])

        mock_av.assert_not_called()
        assert svc.fetch_status["AAPL"] == "ok"

    def test_av_data_stored_with_correct_source_tag(self, svc):
        """Alpha Vantage data should be tagged with source='alpha_vantage'."""
        av_df = pd.DataFrame(
            {
                "Open": [150.0, 151.0],
                "High": [152.0, 153.0],
                "Low": [149.0, 150.0],
                "Close": [151.5, 152.5],
                "Volume": [2000000, 2100000],
            },
            index=pd.DatetimeIndex(
                [pd.Timestamp("2024-06-03"), pd.Timestamp("2024-06-04")], name="Date"
            ),
        )

        with patch.object(svc, "_fetch_with_retry", return_value=None):
            with patch.object(svc, "_fetch_alpha_vantage", return_value=av_df):
                svc.update(["MSFT"])

        with sqlite3.connect(svc.db_path) as conn:
            rows = conn.execute(
                "SELECT ticker, date, source FROM price_history WHERE ticker = 'MSFT' ORDER BY date"
            ).fetchall()

        assert len(rows) == 2
        assert all(r[2] == "alpha_vantage" for r in rows)
