"""
Unit tests for refined trail stop computation in monitor.py.

Tests:
- 2.5% trailing from peak for longs and shorts
- Monotonic ratchet enforcement (never decreases for longs, never increases for shorts)
- Trail activation triggers at P&L > 0%
- ratchet_trail_stop function
- process_take_profit_and_trail_stops with trail activation

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import os
import sys

import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from monitor import (
    compute_trail_stop_level,
    ratchet_trail_stop,
    should_trail_stop_close,
    process_take_profit_and_trail_stops,
)


# ---------------------------------------------------------------------------
# compute_trail_stop_level — 2.5% method tests
# ---------------------------------------------------------------------------


class TestComputeTrailStop25Pct:
    """Test the 2.5% trailing from peak method."""

    def test_long_basic(self):
        """Long: trail = peak * (1 - 0.025)"""
        result = compute_trail_stop_level(100.0, 110.0, "long", method="2.5%")
        assert result == pytest.approx(110.0 * 0.975)

    def test_short_basic(self):
        """Short: trail = peak * (1 + 0.025)"""
        result = compute_trail_stop_level(100.0, 90.0, "short", method="2.5%")
        assert result == pytest.approx(90.0 * 1.025)

    def test_long_default_method(self):
        """Default method is 2.5%."""
        result = compute_trail_stop_level(100.0, 110.0, "long")
        assert result == pytest.approx(110.0 * 0.975)

    def test_long_trail_below_peak(self):
        """For longs, trail stop is always below peak price."""
        peak = 150.0
        result = compute_trail_stop_level(100.0, peak, "long")
        assert result < peak

    def test_short_trail_above_peak(self):
        """For shorts, trail stop is always above peak price (peak is the low)."""
        peak = 85.0
        result = compute_trail_stop_level(100.0, peak, "short")
        assert result > peak

    def test_long_higher_peak_gives_higher_trail(self):
        """Higher peak prices produce higher trail stops for longs."""
        trail_low = compute_trail_stop_level(100.0, 105.0, "long")
        trail_high = compute_trail_stop_level(100.0, 110.0, "long")
        assert trail_high > trail_low

    def test_short_lower_peak_gives_lower_trail(self):
        """Lower peak prices produce lower trail stops for shorts."""
        trail_high = compute_trail_stop_level(100.0, 95.0, "short")
        trail_low = compute_trail_stop_level(100.0, 90.0, "short")
        assert trail_low < trail_high


# ---------------------------------------------------------------------------
# compute_trail_stop_level — 50% legacy method tests
# ---------------------------------------------------------------------------


class TestComputeTrailStop50Pct:
    """Test the 50% legacy method."""

    def test_long_basic(self):
        """Long: trail = entry + 0.5 * (peak - entry)"""
        result = compute_trail_stop_level(100.0, 110.0, "long", method="50%")
        assert result == pytest.approx(105.0)

    def test_short_basic(self):
        """Short: trail = entry - 0.5 * (entry - peak)"""
        result = compute_trail_stop_level(100.0, 90.0, "short", method="50%")
        assert result == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# ratchet_trail_stop tests
# ---------------------------------------------------------------------------


class TestRatchetTrailStop:
    """Test monotonic ratchet enforcement."""

    def test_long_keeps_higher(self):
        """For longs, ratchet keeps the higher trail stop."""
        result = ratchet_trail_stop(105.0, 107.0, "long")
        assert result == 107.0

    def test_long_accepts_new_higher(self):
        """For longs, new higher value replaces existing."""
        result = ratchet_trail_stop(108.0, 105.0, "long")
        assert result == 108.0

    def test_short_keeps_lower(self):
        """For shorts, ratchet keeps the lower trail stop."""
        result = ratchet_trail_stop(95.0, 93.0, "short")
        assert result == 93.0

    def test_short_accepts_new_lower(self):
        """For shorts, new lower value replaces existing."""
        result = ratchet_trail_stop(91.0, 93.0, "short")
        assert result == 91.0

    def test_none_existing_returns_new(self):
        """When no existing level, return the new level."""
        result = ratchet_trail_stop(105.0, None, "long")
        assert result == 105.0

    def test_none_existing_short_returns_new(self):
        """When no existing level (short), return the new level."""
        result = ratchet_trail_stop(95.0, None, "short")
        assert result == 95.0

    def test_long_equal_keeps_same(self):
        """Equal values are fine — stays the same."""
        result = ratchet_trail_stop(105.0, 105.0, "long")
        assert result == 105.0

    def test_long_never_decreases(self):
        """Sequence of trail stops for long never decreases."""
        levels = [100.0, 102.0, 101.0, 103.0, 99.0, 104.0]
        current = None
        for new_level in levels:
            current = ratchet_trail_stop(new_level, current, "long")
        # Should be max of all levels
        assert current == 104.0

    def test_short_never_increases(self):
        """Sequence of trail stops for short never increases."""
        levels = [100.0, 98.0, 99.0, 97.0, 101.0, 96.0]
        current = None
        for new_level in levels:
            current = ratchet_trail_stop(new_level, current, "short")
        # Should be min of all levels
        assert current == 96.0


# ---------------------------------------------------------------------------
# Trail activation logic tests
# ---------------------------------------------------------------------------


class TestTrailActivation:
    """Test that trail stop activates when P&L first exceeds 0%."""

    def test_activates_on_positive_pnl(self):
        """Trail activates when combined_pnl_pct > 0."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 101.0,
                    "combined_pnl_pct": 0.01,  # +1% — above 0%
                    "take_profit": "5%",
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        assert pos.get("trail_activated") is True
        assert pos.get("peak_price") == 101.0
        assert pos.get("trail_stop_level") is not None
        # trail = 101 * (1 - 0.025) = 98.475
        assert pos["trail_stop_level"] == pytest.approx(101.0 * 0.975)

    def test_does_not_activate_on_negative_pnl(self):
        """Trail does NOT activate when P&L is negative."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 99.0,
                    "combined_pnl_pct": -0.01,  # -1%
                    "take_profit": "5%",
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        assert pos.get("trail_activated") is not True
        assert pos.get("trail_stop_level") is None

    def test_does_not_activate_at_zero_pnl(self):
        """Trail does NOT activate when P&L is exactly 0%."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 100.0,
                    "combined_pnl_pct": 0.0,  # exactly 0%
                    "take_profit": "5%",
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        assert pos.get("trail_activated") is not True

    def test_peak_price_ratchets_up_for_long(self):
        """Once trail activated, peak_price only increases for long positions."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 105.0,
                    "combined_pnl_pct": 0.05,
                    "take_profit": "10%",
                    "trail_activated": True,
                    "peak_price": 103.0,  # Previous peak was lower
                    "trail_stop_level": 103.0 * 0.975,
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        # Peak should ratchet up to 105
        assert pos["peak_price"] == 105.0
        # Trail should ratchet up correspondingly
        assert pos["trail_stop_level"] == pytest.approx(105.0 * 0.975)

    def test_peak_price_does_not_decrease_for_long(self):
        """Peak price never decreases for long positions (ratchet)."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 102.0,  # Lower than previous peak
                    "combined_pnl_pct": 0.02,
                    "take_profit": "10%",
                    "trail_activated": True,
                    "peak_price": 105.0,  # Previous peak was higher
                    "trail_stop_level": 105.0 * 0.975,
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        # Peak should stay at 105 (not decrease to 102)
        assert pos["peak_price"] == 105.0
        # Trail stop should not decrease
        assert pos["trail_stop_level"] == pytest.approx(105.0 * 0.975)

    def test_short_trail_activation(self):
        """Trail activates for short positions when P&L > 0%."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "AAPL",
                    "direction": "short",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 98.0,
                    "combined_pnl_pct": 0.02,  # +2% on short
                    "take_profit": "5%",
                }
            ],
        }

        process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        assert pos.get("trail_activated") is True
        assert pos.get("peak_price") == 98.0
        # Short: trail = 98 * (1 + 0.025) = 100.45
        assert pos["trail_stop_level"] == pytest.approx(98.0 * 1.025)

    def test_trail_stop_close_with_trail_activated(self):
        """Position with trail_activated=True closes when price breaches trail."""
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 95.0,  # Below trail stop
                    "combined_pnl_pct": -0.05,
                    "take_profit": "10%",
                    "trail_activated": True,
                    "peak_price": 105.0,
                    "trail_stop_level": 105.0 * 0.975,  # 102.375
                }
            ],
        }

        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)

        pos = book["positions"][0]
        assert pos["status"] == "closed"
        assert pos["exit_reason"] == "trail_stop_auto"
        assert trail_close_count == 1


# ---------------------------------------------------------------------------
# should_trail_stop_close with trail_activated
# ---------------------------------------------------------------------------


class TestShouldTrailStopCloseWithActivation:
    """Test should_trail_stop_close with the new trail_activated flag."""

    def test_trail_activated_long_breached(self):
        """Trail activated long position with price below trail triggers close."""
        pos = {
            "trim_status": "untrimmed",
            "trail_activated": True,
            "trail_stop_level": 102.0,
            "current_price": 100.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is True

    def test_trail_activated_long_not_breached(self):
        """Trail activated long position with price above trail doesn't close."""
        pos = {
            "trim_status": "untrimmed",
            "trail_activated": True,
            "trail_stop_level": 102.0,
            "current_price": 105.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is False

    def test_trail_activated_short_breached(self):
        """Trail activated short position with price above trail triggers close."""
        pos = {
            "trim_status": "untrimmed",
            "trail_activated": True,
            "trail_stop_level": 97.0,
            "current_price": 98.0,
            "direction": "short",
        }
        assert should_trail_stop_close(pos) is True

    def test_no_trail_activated_no_half_trimmed(self):
        """Without trail_activated or half_trimmed, no trail close."""
        pos = {
            "trim_status": "untrimmed",
            "trail_stop_level": 102.0,
            "current_price": 100.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is False
