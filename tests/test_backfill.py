"""
Unit tests for PriceService.backfill_position method.

Tests the backfill coordinator that checks for gaps in price_history
between entry_date and today, skips weekends/holidays, and fetches
missing data via yfinance (with retry) then Alpha Vantage fallback.

Requirements: 11.1, 11.2, 11.3, 11.4
"""

import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_platform.prices import PriceService


@pytest.fixture
def price_service(tmp_path):
    """Create a PriceService with a temporary database."""
    db_path = tmp_path / "test_prices.db"
    return PriceService(db_path=db_path)


def _insert_price_row(price_service, ticker: str, dt: date, close: float = 100.0):
    """Helper to insert a price row into the test database."""
    with sqlite3.connect(price_service.db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO price_history
               (ticker, date, open, high, low, close, volume, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, dt.isoformat(), close, close + 1, close - 1, close, 1000, "yfinance"),
        )


def _make_price_df(dates: list[date], close: float = 100.0) -> pd.DataFrame:
    """Create a mock DataFrame matching yfinance schema for given dates."""
    return pd.DataFrame(
        {
            "Open": [close] * len(dates),
            "High": [close + 1] * len(dates),
            "Low": [close - 1] * len(dates),
            "Close": [close] * len(dates),
            "Volume": [1000] * len(dates),
        },
        index=pd.to_datetime([d.isoformat() for d in dates]),
    )


class TestBackfillNoGaps:
    """Tests for backfill_position when no gaps exist."""

    @patch("src.data_platform.prices.date")
    def test_no_gaps_returns_zero(self, mock_date, price_service):
        """When all expected trading days have data, returns 0 backfilled."""
        # Use a known week: Mon Jan 6 - Fri Jan 10, 2025 (all trading days)
        mock_date.today.return_value = date(2025, 1, 10)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        # Insert data for all 5 trading days
        for i in range(5):
            d = entry + timedelta(days=i)
            _insert_price_row(price_service, "XOM", d)

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            result = price_service.backfill_position("XOM", entry)

        assert result["ticker"] == "XOM"
        assert result["days_backfilled"] == 0
        assert result["gaps_remaining"] == 0

    @patch("src.data_platform.prices.date")
    def test_entry_date_equals_today(self, mock_date, price_service):
        """When entry_date is today and data exists, returns 0 backfilled."""
        today = date(2025, 1, 6)  # Monday
        mock_date.today.return_value = today
        mock_date.fromisoformat = date.fromisoformat

        _insert_price_row(price_service, "SPY", today)

        with patch("src.data_platform.prices.is_trading_day", return_value=True):
            result = price_service.backfill_position("SPY", today)

        assert result["days_backfilled"] == 0
        assert result["gaps_remaining"] == 0


class TestBackfillWithGaps:
    """Tests for backfill_position when gaps exist and data is fetched."""

    @patch("src.data_platform.prices.date")
    def test_gaps_fetched_via_yfinance(self, mock_date, price_service):
        """Gaps are filled via _fetch_with_retry (yfinance)."""
        # Week Mon-Fri: Jan 6-10, 2025. Data exists for Mon, Tue. Missing Wed-Fri.
        mock_date.today.return_value = date(2025, 1, 10)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        _insert_price_row(price_service, "XOM", date(2025, 1, 6))
        _insert_price_row(price_service, "XOM", date(2025, 1, 7))

        missing_dates = [date(2025, 1, 8), date(2025, 1, 9), date(2025, 1, 10)]
        mock_df = _make_price_df(missing_dates)

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            with patch.object(
                price_service, "_fetch_with_retry", return_value=mock_df
            ) as mock_fetch:
                result = price_service.backfill_position("XOM", entry)

        assert result["ticker"] == "XOM"
        assert result["days_backfilled"] == 3
        assert result["gaps_remaining"] == 0
        mock_fetch.assert_called_once()

    @patch("src.data_platform.prices.date")
    def test_fallback_to_alpha_vantage(self, mock_date, price_service):
        """Falls back to Alpha Vantage when yfinance returns None."""
        mock_date.today.return_value = date(2025, 1, 8)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        _insert_price_row(price_service, "XOM", date(2025, 1, 6))
        # Gap: Jan 7, 8

        missing_dates = [date(2025, 1, 7), date(2025, 1, 8)]
        mock_df = _make_price_df(missing_dates)

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            with patch.object(price_service, "_fetch_with_retry", return_value=None):
                with patch.object(
                    price_service, "_fetch_alpha_vantage", return_value=mock_df
                ) as mock_av:
                    result = price_service.backfill_position("XOM", entry)

        assert result["days_backfilled"] == 2
        assert result["gaps_remaining"] == 0
        mock_av.assert_called_once()

        # Verify source tag is alpha_vantage
        with sqlite3.connect(price_service.db_path) as conn:
            row = conn.execute(
                "SELECT source FROM price_history WHERE ticker = ? AND date = ?",
                ("XOM", "2025-01-07"),
            ).fetchone()
        assert row[0] == "alpha_vantage"

    @patch("src.data_platform.prices.date")
    def test_remaining_gaps_when_both_sources_fail(self, mock_date, price_service):
        """Returns gaps_remaining > 0 when both yfinance and AV fail."""
        mock_date.today.return_value = date(2025, 1, 8)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        _insert_price_row(price_service, "XOM", date(2025, 1, 6))
        # Gap: Jan 7, 8

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            with patch.object(price_service, "_fetch_with_retry", return_value=None):
                with patch.object(price_service, "_fetch_alpha_vantage", return_value=None):
                    result = price_service.backfill_position("XOM", entry)

        assert result["ticker"] == "XOM"
        assert result["days_backfilled"] == 0
        assert result["gaps_remaining"] == 2


class TestBackfillWeekendsHolidays:
    """Tests for weekend/holiday exclusion in backfill."""

    @patch("src.data_platform.prices.date")
    def test_weekends_excluded_from_expected_days(self, mock_date, price_service):
        """Weekends are not counted as expected trading days."""
        # Span includes a weekend: Fri Jan 10 - Mon Jan 13
        mock_date.today.return_value = date(2025, 1, 13)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 10)
        # Insert data for Friday and Monday only
        _insert_price_row(price_service, "SPY", date(2025, 1, 10))
        _insert_price_row(price_service, "SPY", date(2025, 1, 13))

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            # Weekdays only (Mon-Fri), Sat/Sun are not trading days
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5

            result = price_service.backfill_position("SPY", entry)

        # Sat Jan 11 and Sun Jan 12 should not be gaps
        assert result["days_backfilled"] == 0
        assert result["gaps_remaining"] == 0

    @patch("src.data_platform.prices.date")
    def test_holidays_excluded_from_expected_days(self, mock_date, price_service):
        """Market holidays are not counted as expected trading days."""
        # MLK Day 2025 is Jan 20 (Monday) — a market holiday
        mock_date.today.return_value = date(2025, 1, 21)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 17)  # Friday before MLK weekend
        _insert_price_row(price_service, "SPY", date(2025, 1, 17))  # Friday
        _insert_price_row(price_service, "SPY", date(2025, 1, 21))  # Tuesday

        def mock_trading_day(dt):
            # Weekends not trading days; MLK Day not a trading day
            if dt.weekday() >= 5:
                return False
            if dt == date(2025, 1, 20):  # MLK Day
                return False
            return True

        with patch("src.data_platform.prices.is_trading_day", side_effect=mock_trading_day):
            result = price_service.backfill_position("SPY", entry)

        # Sat 18, Sun 19, MLK Mon 20 excluded; only Fri 17 and Tue 21 expected
        assert result["days_backfilled"] == 0
        assert result["gaps_remaining"] == 0


class TestBackfillSourceTagging:
    """Tests for correct source tagging during backfill."""

    @patch("src.data_platform.prices.date")
    def test_yfinance_data_tagged_correctly(self, mock_date, price_service):
        """Data fetched via yfinance is tagged with source='yfinance'."""
        mock_date.today.return_value = date(2025, 1, 7)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        _insert_price_row(price_service, "XOM", date(2025, 1, 6))
        # Gap: Jan 7

        mock_df = _make_price_df([date(2025, 1, 7)])

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            with patch.object(price_service, "_fetch_with_retry", return_value=mock_df):
                price_service.backfill_position("XOM", entry)

        with sqlite3.connect(price_service.db_path) as conn:
            row = conn.execute(
                "SELECT source FROM price_history WHERE ticker = ? AND date = ?",
                ("XOM", "2025-01-07"),
            ).fetchone()
        assert row[0] == "yfinance"


class TestBackfillLogging:
    """Tests for backfill logging."""

    @patch("src.data_platform.prices.date")
    def test_backfill_logs_results(self, mock_date, price_service):
        """backfill_position logs ticker, days filled, and gaps remaining."""
        mock_date.today.return_value = date(2025, 1, 8)
        mock_date.fromisoformat = date.fromisoformat

        entry = date(2025, 1, 6)
        _insert_price_row(price_service, "XOM", date(2025, 1, 6))

        mock_df = _make_price_df([date(2025, 1, 7), date(2025, 1, 8)])

        with patch("src.data_platform.prices.is_trading_day") as mock_is_trading:
            mock_is_trading.side_effect = lambda dt: dt.weekday() < 5
            with patch.object(price_service, "_fetch_with_retry", return_value=mock_df):
                with patch("src.data_platform.prices.logger") as mock_logger:
                    result = price_service.backfill_position("XOM", entry)

        mock_logger.info.assert_called_once_with(
            "Backfill %s: %d days filled, %d gaps remaining",
            "XOM", 2, 0,
        )


class TestGroupConsecutiveDates:
    """Tests for the _group_consecutive_dates static method."""

    def test_empty_list(self):
        """Empty list returns empty ranges."""
        assert PriceService._group_consecutive_dates([]) == []

    def test_single_date(self):
        """Single date returns one range of that date."""
        d = date(2025, 1, 6)
        assert PriceService._group_consecutive_dates([d]) == [(d, d)]

    def test_consecutive_weekdays(self):
        """Consecutive weekdays grouped into one range."""
        dates = [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)]
        result = PriceService._group_consecutive_dates(dates)
        assert result == [(date(2025, 1, 6), date(2025, 1, 8))]

    def test_gap_splits_ranges(self):
        """Dates with gaps > 3 days are split into separate ranges."""
        dates = [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 13), date(2025, 1, 14)]
        result = PriceService._group_consecutive_dates(dates)
        assert len(result) == 2
        assert result[0] == (date(2025, 1, 6), date(2025, 1, 7))
        assert result[1] == (date(2025, 1, 13), date(2025, 1, 14))
