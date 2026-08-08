"""
Unit tests for validate_quotes — stale/garbage quote rejection in price_poller.py.

Tests the following behavior (Requirements 22.3, 22.4, 22.5):
- Reject quotes older than 4 hours during market hours (STALE)
- Reject single-tick moves >3% with prior tick <1 hour old that persist on re-fetch (GARBAGE)
- Do not mark positions or trigger trail/target based on stale prices
- Send one Telegram notification on data feed outage, remain quiet until restored
"""

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytz

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_platform.market_calendar import ET
from src.data_platform.prices import PriceService

# Import the functions under test
from scripts.price_poller import (
    GARBAGE_MOVE_THRESHOLD,
    GARBAGE_PRIOR_TICK_MAX_AGE_HOURS,
    STALE_THRESHOLD_HOURS,
    _get_latest_two_quotes,
    _is_garbage_move,
    _is_quote_stale,
    validate_quotes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with price_history table."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def price_service(temp_db):
    """Create a PriceService backed by the temp database."""
    return PriceService(db_path=temp_db)


def _insert_quote(db_path: Path, ticker: str, quote_date: str, close: float):
    """Helper to insert a quote directly into the database."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO price_history (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, quote_date, close, close, close, close, 1000000),
        )


# ---------------------------------------------------------------------------
# Tests for _is_quote_stale
# ---------------------------------------------------------------------------


class TestIsQuoteStale:
    """Tests for the staleness check logic."""

    def test_fresh_quote_is_not_stale(self):
        """A quote from today (during market hours) is not stale."""
        # Simulate current time as 14:00 ET on the same day
        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))
        quote_date = "2025-07-15"

        # Quote at close (16:00) of same day is in the future relative to 14:00
        # but _is_quote_stale assumes close at 16:00 on quote_date
        # 14:00 - 16:00 = -2 hours, not stale
        assert _is_quote_stale(quote_date, now_et) is False

    def test_old_quote_is_stale(self):
        """A quote from 2 days ago is stale during market hours."""
        now_et = ET.localize(datetime(2025, 7, 17, 14, 0, 0))
        quote_date = "2025-07-15"  # 2 days ago

        # Age: 2025-07-17 14:00 - 2025-07-15 16:00 = 46 hours > 4 hours
        assert _is_quote_stale(quote_date, now_et) is True

    def test_quote_exactly_at_threshold(self):
        """A quote exactly 4 hours old is not stale (boundary condition)."""
        now_et = ET.localize(datetime(2025, 7, 15, 20, 0, 0))
        quote_date = "2025-07-15"  # Close at 16:00, now is 20:00 → 4 hours

        # timedelta > 4 hours required, not >=
        assert _is_quote_stale(quote_date, now_et) is False

    def test_quote_just_over_threshold(self):
        """A quote just over 4 hours old is stale."""
        now_et = ET.localize(datetime(2025, 7, 15, 20, 1, 0))
        quote_date = "2025-07-15"  # Close at 16:00, now is 20:01 → 4h1m

        assert _is_quote_stale(quote_date, now_et) is True

    def test_invalid_date_is_stale(self):
        """An invalid/unparseable date is treated as stale."""
        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))
        assert _is_quote_stale("not-a-date", now_et) is True
        assert _is_quote_stale(None, now_et) is True


# ---------------------------------------------------------------------------
# Tests for _is_garbage_move
# ---------------------------------------------------------------------------


class TestIsGarbageMove:
    """Tests for the garbage spike detection logic."""

    def test_small_move_is_not_garbage(self):
        """A move of 2% is below the 3% threshold — not garbage."""
        now_et = ET.localize(datetime(2025, 7, 15, 16, 30, 0))
        prior_date = "2025-07-15"  # Same day → prior age < 1 hour

        current = 102.0
        prior = 100.0  # 2% move

        assert _is_garbage_move(current, prior, prior_date, now_et) is False

    def test_large_move_recent_tick_is_garbage(self):
        """A 5% move with prior tick < 1 hour old is flagged as garbage."""
        now_et = ET.localize(datetime(2025, 7, 15, 16, 30, 0))
        prior_date = "2025-07-15"  # Close at 16:00, 30 min ago → < 1 hour

        current = 105.0
        prior = 100.0  # 5% move

        assert _is_garbage_move(current, prior, prior_date, now_et) is True

    def test_large_move_old_tick_is_not_garbage(self):
        """A 5% move with prior tick > 1 hour old is NOT garbage (could be real)."""
        now_et = ET.localize(datetime(2025, 7, 16, 14, 0, 0))
        prior_date = "2025-07-15"  # Yesterday close → 22 hours ago

        current = 105.0
        prior = 100.0  # 5% move

        assert _is_garbage_move(current, prior, prior_date, now_et) is False

    def test_negative_move_is_garbage(self):
        """A -4% move with recent prior tick is also flagged (absolute move)."""
        now_et = ET.localize(datetime(2025, 7, 15, 16, 30, 0))
        prior_date = "2025-07-15"

        current = 96.0
        prior = 100.0  # -4% move

        assert _is_garbage_move(current, prior, prior_date, now_et) is True

    def test_zero_prior_close_not_garbage(self):
        """Prior close of 0 should not cause division error."""
        now_et = ET.localize(datetime(2025, 7, 15, 16, 30, 0))
        assert _is_garbage_move(100.0, 0.0, "2025-07-15", now_et) is False

    def test_invalid_prior_date_not_garbage(self):
        """Invalid prior date should not flag as garbage."""
        now_et = ET.localize(datetime(2025, 7, 15, 16, 30, 0))
        assert _is_garbage_move(105.0, 100.0, "bad-date", now_et) is False


# ---------------------------------------------------------------------------
# Tests for validate_quotes (integration)
# ---------------------------------------------------------------------------


class TestValidateQuotes:
    """Integration tests for the full validate_quotes function."""

    def test_fresh_quotes_pass_validation(self, price_service, temp_db):
        """Fresh quotes during market hours pass validation."""
        # Insert a quote from today
        _insert_quote(temp_db, "AAPL", "2025-07-15", 150.0)
        _insert_quote(temp_db, "AAPL", "2025-07-14", 148.0)

        # Set time during market hours, same day as quote
        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            result = validate_quotes(["AAPL"], price_service, now_et=now_et)

        assert "AAPL" in result
        assert result["AAPL"] == 150.0

    def test_stale_quotes_rejected_during_market_hours(self, price_service, temp_db):
        """Quotes older than 4 hours are rejected during market hours."""
        # Insert a quote from 3 days ago
        _insert_quote(temp_db, "AAPL", "2025-07-12", 150.0)

        # Current time: 2025-07-15 10:00 ET (market hours)
        now_et = ET.localize(datetime(2025, 7, 15, 10, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            result = validate_quotes(["AAPL"], price_service, now_et=now_et)

        assert "AAPL" not in result

    def test_stale_quotes_accepted_outside_market_hours(self, price_service, temp_db):
        """Stale quotes are accepted when market is closed (no staleness check)."""
        # Insert a quote from 3 days ago
        _insert_quote(temp_db, "AAPL", "2025-07-12", 150.0)

        # Current time: Saturday (market closed)
        now_et = ET.localize(datetime(2025, 7, 12, 20, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=False):
            result = validate_quotes(["AAPL"], price_service, now_et=now_et)

        assert "AAPL" in result

    def test_garbage_quote_rejected_on_refetch_confirm(self, price_service, temp_db):
        """A garbage spike that persists after re-fetch is rejected."""
        # Insert two quotes: prior is recent, current is a >3% spike
        _insert_quote(temp_db, "XOM", "2025-07-15", 105.0)  # 5% spike
        _insert_quote(temp_db, "XOM", "2025-07-14", 100.0)  # prior from yesterday

        # Set time just after market close (prior tick < 1 hour old)
        # Actually for garbage check, the prior_date needs to be very recent
        # Let's set now to 2025-07-15 16:30 and prior from same day
        _insert_quote(temp_db, "SPY", "2025-07-15", 450.0)
        _insert_quote(temp_db, "SPY", "2025-07-15", 450.0)

        # For XOM: current=105, prior date=2025-07-15 (today close at 16:00)
        # now=16:30 → prior is 30 min old < 1 hour. Move is 5% > 3%.
        # But we need prior_date to be today for the garbage check
        # Adjust: insert prior as today
        with sqlite3.connect(temp_db) as conn:
            conn.execute("DELETE FROM price_history WHERE ticker = 'XOM'")
            conn.execute(
                "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("XOM", "2025-07-15", 105, 105, 105, 105.0, 1000000),
            )
            conn.execute(
                "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("XOM", "2025-07-14", 100, 100, 100, 100.0, 1000000),
            )

        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        # Mock re-fetch to not actually call yfinance but leave DB unchanged
        # (so the spike persists → garbage confirmed)
        with patch("scripts.price_poller.is_market_open", return_value=True):
            with patch.object(price_service, "update", return_value=0):
                result = validate_quotes(["XOM"], price_service, now_et=now_et)

        # For this test, prior_date is "2025-07-14" → prior age at 14:00 on July 15
        # = (2025-07-15 14:00) - (2025-07-14 16:00) = 22 hours > 1 hour
        # So it won't be flagged as garbage (prior too old)
        # Let's adjust: make both dates same day for proper garbage detection
        with sqlite3.connect(temp_db) as conn:
            conn.execute("DELETE FROM price_history WHERE ticker = 'XOM'")
            # Two ticks on the same day (simulating intraday) — but DB uses date granularity
            # For the garbage check to trigger, prior_date must be within 1 hour
            # In practice with EOD data, this means prior_date == today
            conn.execute(
                "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("XOM", "2025-07-15", 105, 105, 105, 105.0, 1000000),
            )
            conn.execute(
                "INSERT INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("XOM", "2025-07-14", 100, 100, 100, 100.0, 1000000),
            )

        # To trigger garbage: now must be within 1 hour of prior's assumed close (16:00)
        # Prior is 2025-07-14 close at 16:00. now = 2025-07-14 16:30 → age = 30min < 1hr
        now_et = ET.localize(datetime(2025, 7, 14, 16, 30, 0))

        with patch("scripts.price_poller.is_market_open", return_value=False):
            with patch.object(price_service, "update", return_value=0):
                result = validate_quotes(["XOM"], price_service, now_et=now_et)

        # XOM should be rejected as garbage (move persists after re-fetch)
        assert "XOM" not in result

    def test_garbage_quote_accepted_on_refetch_correction(self, price_service, temp_db):
        """A garbage spike that corrects on re-fetch is accepted with new value."""
        # Insert spike: current = 105, prior = 100
        _insert_quote(temp_db, "XOM", "2025-07-15", 105.0)
        _insert_quote(temp_db, "XOM", "2025-07-14", 100.0)

        # Now is within 1 hour of prior close
        now_et = ET.localize(datetime(2025, 7, 14, 16, 30, 0))

        def mock_update(tickers, lookback_days=1):
            """Simulate re-fetch that corrects the spike."""
            with sqlite3.connect(temp_db) as conn:
                conn.execute(
                    "UPDATE price_history SET close = ? WHERE ticker = ? AND date = ?",
                    (101.0, "XOM", "2025-07-15"),
                )
            return 1

        with patch("scripts.price_poller.is_market_open", return_value=False):
            with patch.object(price_service, "update", side_effect=mock_update):
                result = validate_quotes(["XOM"], price_service, now_et=now_et)

        # XOM should be accepted with the corrected value
        assert "XOM" in result
        assert result["XOM"] == 101.0

    def test_outage_detection_all_stale(self, price_service, temp_db):
        """When all tickers are stale during market hours, an outage alert is sent."""
        import scripts.price_poller as poller_module

        # Reset outage state
        poller_module._outage_alert_sent = False
        poller_module._last_good_time = ET.localize(datetime(2025, 7, 14, 15, 0, 0))

        # Insert old quotes for all tickers
        _insert_quote(temp_db, "AAPL", "2025-07-12", 150.0)
        _insert_quote(temp_db, "MSFT", "2025-07-12", 300.0)

        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            with patch("scripts.price_poller.send_telegram") as mock_telegram:
                result = validate_quotes(
                    ["AAPL", "MSFT"], price_service, now_et=now_et
                )

        # No valid quotes
        assert result == {}

        # Telegram was called exactly once
        mock_telegram.assert_called_once()
        call_text = mock_telegram.call_args[0][0]
        assert "Data feed outage" in call_text
        assert "2025-07-14 15:00 ET" in call_text

    def test_outage_alert_not_repeated(self, price_service, temp_db):
        """Once outage alert is sent, it should not be repeated on subsequent cycles."""
        import scripts.price_poller as poller_module

        # Simulate alert already sent
        poller_module._outage_alert_sent = True
        poller_module._last_good_time = ET.localize(datetime(2025, 7, 14, 15, 0, 0))

        _insert_quote(temp_db, "AAPL", "2025-07-12", 150.0)

        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            with patch("scripts.price_poller.send_telegram") as mock_telegram:
                validate_quotes(["AAPL"], price_service, now_et=now_et)

        # Telegram should NOT be called again
        mock_telegram.assert_not_called()

    def test_outage_clears_on_feed_restoration(self, price_service, temp_db):
        """When feed is restored, outage state is cleared."""
        import scripts.price_poller as poller_module

        # Simulate prior outage
        poller_module._outage_alert_sent = True
        poller_module._last_good_time = ET.localize(datetime(2025, 7, 14, 15, 0, 0))

        # Insert a fresh quote
        _insert_quote(temp_db, "AAPL", "2025-07-15", 150.0)

        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            result = validate_quotes(["AAPL"], price_service, now_et=now_et)

        assert "AAPL" in result
        # Outage state should be cleared
        assert poller_module._outage_alert_sent is False
        assert poller_module._last_good_time == now_et

    def test_empty_tickers_returns_empty(self, price_service):
        """Passing an empty ticker list returns an empty dict."""
        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            result = validate_quotes([], price_service, now_et=now_et)

        assert result == {}

    def test_ticker_with_no_data_counted_as_stale(self, price_service):
        """A ticker with no data in DB is counted as stale."""
        now_et = ET.localize(datetime(2025, 7, 15, 14, 0, 0))

        with patch("scripts.price_poller.is_market_open", return_value=True):
            result = validate_quotes(["UNKNOWN"], price_service, now_et=now_et)

        assert "UNKNOWN" not in result


# ---------------------------------------------------------------------------
# Tests for _get_latest_two_quotes
# ---------------------------------------------------------------------------


class TestGetLatestTwoQuotes:
    """Tests for the quote retrieval helper."""

    def test_returns_two_quotes_in_order(self, price_service, temp_db):
        """Returns quotes in most-recent-first order."""
        _insert_quote(temp_db, "AAPL", "2025-07-14", 148.0)
        _insert_quote(temp_db, "AAPL", "2025-07-15", 150.0)
        _insert_quote(temp_db, "AAPL", "2025-07-13", 147.0)

        quotes = _get_latest_two_quotes("AAPL", price_service)

        assert len(quotes) == 2
        assert quotes[0]["date"] == "2025-07-15"
        assert quotes[0]["close"] == 150.0
        assert quotes[1]["date"] == "2025-07-14"
        assert quotes[1]["close"] == 148.0

    def test_returns_empty_for_unknown_ticker(self, price_service):
        """Returns empty list for a ticker with no data."""
        quotes = _get_latest_two_quotes("NONEXISTENT", price_service)
        assert quotes == []

    def test_returns_one_quote_if_only_one_exists(self, price_service, temp_db):
        """Returns a single quote if only one row exists."""
        _insert_quote(temp_db, "AAPL", "2025-07-15", 150.0)

        quotes = _get_latest_two_quotes("AAPL", price_service)

        assert len(quotes) == 1
        assert quotes[0]["close"] == 150.0
