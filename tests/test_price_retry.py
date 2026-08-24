"""
Unit tests for PriceService exponential backoff retry logic.

Tests the _fetch_with_retry method and fetch_status tracking
added to src/data_platform/prices.py.

Requirements: 1.1, 1.2, 1.3
"""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_platform.prices import PriceService


@pytest.fixture
def price_service(tmp_path):
    """Create a PriceService with a temporary database."""
    db_path = tmp_path / "test_prices.db"
    return PriceService(db_path=db_path)


class TestFetchWithRetry:
    """Tests for PriceService._fetch_with_retry."""

    def test_success_on_first_attempt(self, price_service):
        """Returns DataFrame immediately when first attempt succeeds."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", return_value=mock_df) as mock_download:
            result = price_service._fetch_with_retry("SPY", date(2025, 1, 1))

        assert result is not None
        assert not result.empty
        assert mock_download.call_count == 1

    def test_success_after_one_retry(self, price_service):
        """Returns DataFrame after one failed attempt and one success."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", side_effect=[Exception("timeout"), mock_df]) as mock_download:
            with patch("time.sleep") as mock_sleep:
                result = price_service._fetch_with_retry("SPY", date(2025, 1, 1))

        assert result is not None
        assert not result.empty
        assert mock_download.call_count == 2
        mock_sleep.assert_called_once_with(2)  # 2^(0+1) = 2s

    def test_success_after_two_retries(self, price_service):
        """Returns DataFrame after two failed attempts."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", side_effect=[
            Exception("timeout"), Exception("connection reset"), mock_df
        ]) as mock_download:
            with patch("time.sleep") as mock_sleep:
                result = price_service._fetch_with_retry("SPY", date(2025, 1, 1))

        assert result is not None
        assert mock_download.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)  # 2^(0+1) = 2s
        mock_sleep.assert_any_call(4)  # 2^(1+1) = 4s

    def test_returns_none_after_all_retries_exhausted(self, price_service):
        """Returns None when all attempts (initial + 3 retries) fail."""
        with patch("yfinance.download", side_effect=Exception("persistent failure")) as mock_download:
            with patch("time.sleep") as mock_sleep:
                result = price_service._fetch_with_retry("BADTICKER", date(2025, 1, 1))

        assert result is None
        assert mock_download.call_count == 4  # initial + 3 retries
        assert mock_sleep.call_count == 3
        mock_sleep.assert_any_call(2)  # 2^1
        mock_sleep.assert_any_call(4)  # 2^2
        mock_sleep.assert_any_call(8)  # 2^3

    def test_backoff_delays_are_exponential(self, price_service):
        """Verify delays follow 2^(attempt+1) pattern: 2, 4, 8 seconds."""
        with patch("yfinance.download", side_effect=Exception("fail")):
            with patch("time.sleep") as mock_sleep:
                price_service._fetch_with_retry("XOM", date(2025, 1, 1))

        expected_delays = [2, 4, 8]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays

    def test_returns_empty_dataframe_on_no_data(self, price_service):
        """Returns empty DataFrame when yfinance returns empty (no exception)."""
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            result = price_service._fetch_with_retry("SPY", date(2025, 1, 1))

        assert result is not None
        assert result.empty

    def test_flattens_multiindex_columns(self, price_service):
        """Flattens yfinance MultiIndex columns for single-ticker downloads."""
        # Simulate yfinance 1.2+ MultiIndex
        arrays = [
            ["Open", "High", "Low", "Close", "Volume"],
            ["SPY", "SPY", "SPY", "SPY", "SPY"],
        ]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples)
        mock_df = pd.DataFrame(
            [[100.0, 105.0, 99.0, 103.0, 1000]],
            columns=index,
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", return_value=mock_df):
            result = price_service._fetch_with_retry("SPY", date(2025, 1, 1))

        assert result is not None
        # After flattening, columns should be first level only
        assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]

    def test_custom_max_retries(self, price_service):
        """Respects custom max_retries parameter."""
        with patch("yfinance.download", side_effect=Exception("fail")):
            with patch("time.sleep") as mock_sleep:
                result = price_service._fetch_with_retry("XOM", date(2025, 1, 1), max_retries=1)

        assert result is None
        assert mock_sleep.call_count == 1  # Only 1 retry


class TestFetchStatus:
    """Tests for fetch_status tracking in PriceService."""

    def test_fetch_status_initialized_empty(self, price_service):
        """fetch_status is an empty dict on initialization."""
        assert price_service.fetch_status == {}

    def test_get_fetch_status_defaults_to_ok(self, price_service):
        """get_fetch_status returns 'ok' for untracked tickers."""
        assert price_service.get_fetch_status("UNKNOWN") == "ok"

    def test_fetch_status_ok_on_success(self, price_service):
        """Successful fetch sets status to 'ok'."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", return_value=mock_df):
            with patch("time.sleep"):
                price_service.update(["SPY"])

        assert price_service.get_fetch_status("SPY") == "ok"

    def test_fetch_status_failed_on_exhaustion(self, price_service):
        """Failed fetch (all retries exhausted, no AV key) sets status to 'unfetchable'."""
        with patch("yfinance.download", side_effect=Exception("persistent failure")):
            with patch("time.sleep"):
                price_service.update(["BADTICKER"])

        # When both yfinance and Alpha Vantage fail (no key set), status is "unfetchable"
        assert price_service.get_fetch_status("BADTICKER") == "unfetchable"

    def test_fetch_status_reset_each_update(self, price_service):
        """fetch_status is cleared at the start of each update() call."""
        # First update: mark one ticker as failed
        with patch("yfinance.download", side_effect=Exception("fail")):
            with patch("time.sleep"):
                price_service.update(["FAIL1"])

        assert price_service.get_fetch_status("FAIL1") == "unfetchable"

        # Second update with different tickers: previous status cleared
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )
        with patch("yfinance.download", return_value=mock_df):
            with patch("time.sleep"):
                price_service.update(["SPY"])

        # FAIL1 is no longer in fetch_status (cleared), defaults to "ok"
        assert price_service.get_fetch_status("FAIL1") == "ok"
        assert price_service.get_fetch_status("SPY") == "ok"

    def test_fetch_status_ok_when_already_up_to_date(self, price_service):
        """Tickers that are already up to date get status 'ok'."""
        # Insert a row for today so the ticker appears up-to-date
        import sqlite3
        today_str = date.today().isoformat()
        with sqlite3.connect(price_service.db_path) as conn:
            conn.execute(
                "INSERT INTO price_history (ticker, date, close, source) VALUES (?, ?, ?, ?)",
                ("SPY", today_str, 500.0, "yfinance"),
            )

        price_service.update(["SPY"])
        assert price_service.get_fetch_status("SPY") == "ok"

    def test_fetch_status_ok_on_empty_dataframe(self, price_service):
        """Empty DataFrame (no new data) sets status to 'ok'."""
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            with patch("time.sleep"):
                price_service.update(["SPY"])

        assert price_service.get_fetch_status("SPY") == "ok"


class TestUpdateWithRetry:
    """Tests for the modified update() method."""

    def test_update_inserts_rows_on_success(self, price_service):
        """update() inserts rows into the database on successful fetch."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        with patch("yfinance.download", return_value=mock_df):
            inserted = price_service.update(["SPY"])

        assert inserted == 1
        assert price_service.has_data("SPY")

    def test_update_continues_on_failure(self, price_service):
        """update() continues processing remaining tickers after a failure."""
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        # First ticker fails (4 attempts), second succeeds
        with patch("yfinance.download", side_effect=[
            Exception("fail"), Exception("fail"), Exception("fail"), Exception("fail"),
            mock_df,
        ]):
            with patch("time.sleep"):
                inserted = price_service.update(["FAIL", "SPY"])

        assert price_service.get_fetch_status("FAIL") == "unfetchable"
        assert price_service.get_fetch_status("SPY") == "ok"
        assert inserted == 1

    def test_update_returns_total_rows_inserted(self, price_service):
        """update() returns the total number of rows inserted across all tickers."""
        mock_df = pd.DataFrame(
            {"Open": [100.0, 101.0], "High": [105.0, 106.0], "Low": [99.0, 100.0],
             "Close": [103.0, 104.0], "Volume": [1000, 1100]},
            index=pd.to_datetime(["2025-01-02", "2025-01-03"]),
        )

        with patch("yfinance.download", return_value=mock_df):
            inserted = price_service.update(["SPY", "XLE"])

        assert inserted == 4  # 2 rows * 2 tickers
