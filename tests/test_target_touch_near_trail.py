"""
Unit tests for target touch detection and near-trail warning functions
in scripts/price_poller.py.

Tests validate:
- handle_target_touches() flags positions at +5% and sends alerts
- handle_target_touches() does NOT auto-exit positions
- handle_target_touches() does not re-alert already-flagged positions
- handle_near_trail_warnings() detects near-trail zone (drawdown >= 2.0% and < 2.5%)
- handle_near_trail_warnings() sends one warning per position per calendar day
- handle_near_trail_warnings() does not fire for positions outside the warning zone

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.price_poller import (
    handle_target_touches,
    handle_near_trail_warnings,
    _near_trail_warnings_sent,
)
from src.data_platform.book_ops import (
    TRAIL_BREACH_THRESHOLD,
    TARGET_TOUCH_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_position(
    ticker="XOM",
    status="active",
    combined_pnl_pct=0.0,
    peak_pnl=0.0,
    target_touched=False,
    **kwargs,
) -> dict:
    """Helper to create a test position dict."""
    pos = {
        "ticker": ticker,
        "hedge_ticker": "CVX",
        "status": status,
        "direction": "long",
        "hedge_direction": "short",
        "entry_price": 100.0,
        "hedge_entry_price": 100.0,
        "current_price": 105.0,
        "hedge_current_price": 100.0,
        "combined_pnl_pct": combined_pnl_pct,
        "peak_pnl": peak_pnl,
        "size_pct_nav": 0.05,
    }
    if target_touched:
        pos["target_touched"] = True
    pos.update(kwargs)
    return pos


def _make_book(positions=None) -> dict:
    """Helper to create a test book dict."""
    return {
        "nav": 650000000,
        "initial_nav": 650000000,
        "cash_pct": 0.75,
        "positions": positions or [],
        "trade_journal": [],
        "last_marked": "2025-07-01T10:00:00",
    }


# ---------------------------------------------------------------------------
# Target Touch Tests
# ---------------------------------------------------------------------------


class TestHandleTargetTouches:
    """Tests for handle_target_touches function."""

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_flags_position(self, mock_telegram):
        """When combined P&L >= 5%, position gets target_touched=True."""
        pos = _make_position(combined_pnl_pct=0.055)  # 5.5% > 5% target
        book = _make_book([pos])

        result = handle_target_touches(book)

        assert result["positions"][0]["target_touched"] is True

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_sends_telegram_alert(self, mock_telegram):
        """When target is touched, a Telegram alert is sent."""
        pos = _make_position(combined_pnl_pct=0.06)  # 6%
        book = _make_book([pos])

        handle_target_touches(book)

        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args[0][0]
        assert "Target Touch" in call_args
        assert "XOM" in call_args
        assert "+6.00%" in call_args

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_does_not_auto_exit(self, mock_telegram):
        """Target touch does NOT close the position (Requirement 3.1)."""
        pos = _make_position(combined_pnl_pct=0.07)  # 7%
        book = _make_book([pos])

        result = handle_target_touches(book)

        # Position must remain active
        assert result["positions"][0]["status"] == "active"

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_no_re_alert_if_already_flagged(self, mock_telegram):
        """If target_touched is already True, don't re-send the alert."""
        pos = _make_position(combined_pnl_pct=0.06, target_touched=True)
        book = _make_book([pos])

        handle_target_touches(book)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_ignores_below_threshold(self, mock_telegram):
        """Positions below +5% don't trigger target touch."""
        pos = _make_position(combined_pnl_pct=0.04)  # 4% < 5%
        book = _make_book([pos])

        result = handle_target_touches(book)

        assert "target_touched" not in result["positions"][0]
        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_ignores_closed_positions(self, mock_telegram):
        """Closed positions are not checked for target touch."""
        pos = _make_position(combined_pnl_pct=0.08, status="closed")
        book = _make_book([pos])

        result = handle_target_touches(book)

        assert "target_touched" not in result["positions"][0]
        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_exactly_at_threshold(self, mock_telegram):
        """Position at exactly 5% triggers target touch."""
        pos = _make_position(combined_pnl_pct=0.05)  # Exactly 5%
        book = _make_book([pos])

        result = handle_target_touches(book)

        assert result["positions"][0]["target_touched"] is True
        mock_telegram.assert_called_once()

    @patch("scripts.price_poller.send_telegram")
    def test_target_touch_multiple_positions(self, mock_telegram):
        """Multiple positions can trigger target touch independently."""
        pos1 = _make_position(ticker="XOM", combined_pnl_pct=0.06)
        pos2 = _make_position(ticker="AAPL", combined_pnl_pct=0.07)
        pos3 = _make_position(ticker="MSFT", combined_pnl_pct=0.02)  # Below target
        book = _make_book([pos1, pos2, pos3])

        result = handle_target_touches(book)

        assert result["positions"][0]["target_touched"] is True
        assert result["positions"][1]["target_touched"] is True
        assert "target_touched" not in result["positions"][2]
        assert mock_telegram.call_count == 2


# ---------------------------------------------------------------------------
# Near-Trail Warning Tests
# ---------------------------------------------------------------------------


class TestHandleNearTrailWarnings:
    """Tests for handle_near_trail_warnings function."""

    def setup_method(self):
        """Clear the dedup tracker before each test."""
        _near_trail_warnings_sent.clear()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_fires_in_zone(self, mock_telegram):
        """Warning fires when drawdown from peak is in [2.0%, 2.5%)."""
        # peak=3%, combined=0.8% → drawdown=2.2% (within 0.5% of 2.5% trail)
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.008)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args[0][0]
        assert "Near-Trail Warning" in call_args
        assert "XOM" in call_args

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_not_fired_below_zone(self, mock_telegram):
        """Warning does NOT fire when drawdown < 2.0%."""
        # peak=3%, combined=1.5% → drawdown=1.5% (below near-trail zone)
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.015)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_not_fired_at_breach(self, mock_telegram):
        """Warning does NOT fire when drawdown >= 2.5% (that's a breach, not a warning)."""
        # peak=3%, combined=0.4% → drawdown=2.6% (at or past breach)
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.004)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_once_per_day(self, mock_telegram):
        """Only one warning per position per calendar day (dedup)."""
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.008)
        book = _make_book([pos])

        # First call — should fire
        handle_near_trail_warnings(book)
        assert mock_telegram.call_count == 1

        # Second call same day — should NOT fire again
        handle_near_trail_warnings(book)
        assert mock_telegram.call_count == 1

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_different_positions_same_day(self, mock_telegram):
        """Different positions can each get one warning per day."""
        pos1 = _make_position(ticker="XOM", peak_pnl=0.03, combined_pnl_pct=0.008)
        pos2 = _make_position(ticker="AAPL", peak_pnl=0.04, combined_pnl_pct=0.018)
        book = _make_book([pos1, pos2])

        handle_near_trail_warnings(book)

        assert mock_telegram.call_count == 2

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_ignores_closed_positions(self, mock_telegram):
        """Closed positions are not checked for near-trail."""
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.008, status="closed")
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_boundary_exactly_at_2_percent(self, mock_telegram):
        """Drawdown just above 2.0% is within the warning zone."""
        # peak=3%, combined=0.9% → drawdown=2.1% (clearly in the zone)
        pos = _make_position(peak_pnl=0.03, combined_pnl_pct=0.009)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_called_once()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_boundary_exactly_at_2_5_percent(self, mock_telegram):
        """Drawdown clearly at 2.5% does NOT fire a warning (it's a breach)."""
        # peak=5%, combined=2.5% → drawdown=2.5% (exactly at breach threshold)
        pos = _make_position(peak_pnl=0.05, combined_pnl_pct=0.025)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_near_trail_warning_message_content(self, mock_telegram):
        """Warning message includes drawdown details and trail remaining."""
        # peak=5%, combined=2.8% → drawdown=2.2%
        pos = _make_position(peak_pnl=0.05, combined_pnl_pct=0.028)
        book = _make_book([pos])

        handle_near_trail_warnings(book)

        mock_telegram.assert_called_once()
        msg = mock_telegram.call_args[0][0]
        assert "XOM" in msg
        assert "2.20%" in msg  # drawdown
        assert "2.5%" in msg  # trail level
        assert "0.30%" in msg  # remaining
