"""
Unit tests for take-profit trim and trail stop logic in monitor.py.

Tests the functions:
- parse_take_profit_level: extracts percentage from strings
- should_trim: determines if position is ready for trim
- compute_trail_stop_level: computes 50% gain trail stop
- should_trail_stop_close: determines if trail stop is breached
- execute_trim: halves position and sets trail stop
- execute_trail_stop_close: fully closes trailed position
- process_take_profit_and_trail_stops: integration of trim/trail in monitor

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import os
import sys
from datetime import date

import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from monitor import (
    parse_take_profit_level,
    should_trim,
    compute_trail_stop_level,
    ratchet_trail_stop,
    should_trail_stop_close,
    execute_trim,
    execute_trail_stop_close,
    process_take_profit_and_trail_stops,
)


# ---------------------------------------------------------------------------
# parse_take_profit_level tests
# ---------------------------------------------------------------------------


class TestParseTakeProfitLevel:
    def test_simple_percentage(self):
        assert parse_take_profit_level("5%") == 0.05

    def test_percentage_with_description(self):
        assert parse_take_profit_level("5% triggers review") == 0.05

    def test_three_percent(self):
        assert parse_take_profit_level("3% target") == 0.03

    def test_decimal_percentage(self):
        assert parse_take_profit_level("7.5% upside target") == 0.075

    def test_no_percentage_returns_default(self):
        assert parse_take_profit_level("review at target") == 0.05

    def test_empty_string_returns_default(self):
        assert parse_take_profit_level("") == 0.05

    def test_none_returns_default(self):
        # The function guards against None with `if not take_profit_str`
        assert parse_take_profit_level(None) == 0.05


# ---------------------------------------------------------------------------
# should_trim tests
# ---------------------------------------------------------------------------


class TestShouldTrim:
    def test_untrimmed_above_target(self):
        pos = {
            "trim_status": "untrimmed",
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        assert should_trim(pos) is True

    def test_untrimmed_exactly_at_target(self):
        pos = {
            "trim_status": "untrimmed",
            "combined_pnl_pct": 0.05,
            "take_profit": "5%",
        }
        assert should_trim(pos) is True

    def test_untrimmed_below_target(self):
        pos = {
            "trim_status": "untrimmed",
            "combined_pnl_pct": 0.04,
            "take_profit": "5%",
        }
        assert should_trim(pos) is False

    def test_already_half_trimmed(self):
        pos = {
            "trim_status": "half_trimmed",
            "combined_pnl_pct": 0.08,
            "take_profit": "5%",
        }
        assert should_trim(pos) is False

    def test_fully_exited(self):
        pos = {
            "trim_status": "fully_exited",
            "combined_pnl_pct": 0.10,
            "take_profit": "5%",
        }
        assert should_trim(pos) is False

    def test_no_trim_status_defaults_untrimmed(self):
        pos = {
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        assert should_trim(pos) is True

    def test_no_combined_pnl(self):
        pos = {
            "trim_status": "untrimmed",
            "take_profit": "5%",
        }
        assert should_trim(pos) is False

    def test_custom_take_profit_level(self):
        pos = {
            "trim_status": "untrimmed",
            "combined_pnl_pct": 0.04,
            "take_profit": "3% triggers review",
        }
        assert should_trim(pos) is True


# ---------------------------------------------------------------------------
# compute_trail_stop_level tests
# ---------------------------------------------------------------------------


class TestComputeTrailStopLevel:
    """Tests for compute_trail_stop_level with both 2.5% and 50% methods."""

    # --- 2.5% trailing from peak (default) ---

    def test_long_position_2_5_pct(self):
        # entry=100, peak=106
        # trail = 106 * (1 - 0.025) = 103.35
        result = compute_trail_stop_level(100.0, 106.0, "long")
        assert result == pytest.approx(106.0 * 0.975)

    def test_short_position_2_5_pct(self):
        # entry=100, peak=94 (price went down for short profit)
        # trail = 94 * (1 + 0.025) = 96.35
        result = compute_trail_stop_level(100.0, 94.0, "short")
        assert result == pytest.approx(94.0 * 1.025)

    def test_long_large_gain_2_5_pct(self):
        # entry=50, peak=60
        # trail = 60 * 0.975 = 58.5
        result = compute_trail_stop_level(50.0, 60.0, "long")
        assert result == pytest.approx(60.0 * 0.975)

    def test_short_large_gain_2_5_pct(self):
        # entry=200, peak=180
        # trail = 180 * 1.025 = 184.5
        result = compute_trail_stop_level(200.0, 180.0, "short")
        assert result == pytest.approx(180.0 * 1.025)

    def test_explicit_method_2_5_pct(self):
        # Explicit method="2.5%"
        result = compute_trail_stop_level(100.0, 110.0, "long", method="2.5%")
        assert result == pytest.approx(110.0 * 0.975)

    # --- 50% legacy method ---

    def test_long_position_50pct(self):
        # entry=100, peak=106
        # trail = 100 + 0.5 * (106 - 100) = 103
        result = compute_trail_stop_level(100.0, 106.0, "long", method="50%")
        assert result == pytest.approx(103.0)

    def test_short_position_50pct(self):
        # entry=100, peak=94
        # trail = 100 - 0.5 * (100 - 94) = 97
        result = compute_trail_stop_level(100.0, 94.0, "short", method="50%")
        assert result == pytest.approx(97.0)

    def test_long_large_gain_50pct(self):
        # entry=50, peak=60
        # trail = 50 + 0.5 * 10 = 55
        result = compute_trail_stop_level(50.0, 60.0, "long", method="50%")
        assert result == pytest.approx(55.0)

    def test_short_large_gain_50pct(self):
        # entry=200, peak=180
        # trail = 200 - 0.5 * 20 = 190
        result = compute_trail_stop_level(200.0, 180.0, "short", method="50%")
        assert result == pytest.approx(190.0)

    def test_trail_is_midpoint_long_50pct(self):
        # Trail stop should be exactly at the midpoint between entry and peak
        entry = 100.0
        peak = 110.0
        result = compute_trail_stop_level(entry, peak, "long", method="50%")
        midpoint = (entry + peak) / 2
        assert result == pytest.approx(midpoint)

    def test_trail_is_midpoint_short_50pct(self):
        # For short, midpoint between current (peak) and entry
        entry = 100.0
        peak = 90.0
        result = compute_trail_stop_level(entry, peak, "short", method="50%")
        midpoint = (entry + peak) / 2
        assert result == pytest.approx(midpoint)


# ---------------------------------------------------------------------------
# should_trail_stop_close tests
# ---------------------------------------------------------------------------


class TestShouldTrailStopClose:
    def test_long_price_below_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "current_price": 102.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is True

    def test_long_price_at_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "current_price": 103.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is True

    def test_long_price_above_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "current_price": 105.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is False

    def test_short_price_above_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 97.0,
            "current_price": 98.0,
            "direction": "short",
        }
        assert should_trail_stop_close(pos) is True

    def test_short_price_at_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 97.0,
            "current_price": 97.0,
            "direction": "short",
        }
        assert should_trail_stop_close(pos) is True

    def test_short_price_below_trail(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": 97.0,
            "current_price": 95.0,
            "direction": "short",
        }
        assert should_trail_stop_close(pos) is False

    def test_not_half_trimmed(self):
        pos = {
            "trim_status": "untrimmed",
            "trail_stop_level": 103.0,
            "current_price": 100.0,
            "direction": "long",
        }
        # Without trail_activated, untrimmed position doesn't trigger trail close
        assert should_trail_stop_close(pos) is False

    def test_trail_activated_triggers_close(self):
        pos = {
            "trim_status": "untrimmed",
            "trail_activated": True,
            "trail_stop_level": 103.0,
            "current_price": 100.0,
            "direction": "long",
        }
        # With trail_activated=True, even untrimmed position can trigger trail close
        assert should_trail_stop_close(pos) is True

    def test_no_trail_level(self):
        pos = {
            "trim_status": "half_trimmed",
            "trail_stop_level": None,
            "current_price": 100.0,
            "direction": "long",
        }
        assert should_trail_stop_close(pos) is False


# ---------------------------------------------------------------------------
# execute_trim tests
# ---------------------------------------------------------------------------


class TestExecuteTrim:
    def test_halves_position_size(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.04,
            "entry_price": 100.0,
            "current_price": 106.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        assert pos["size_pct_nav"] == pytest.approx(0.02)

    def test_sets_half_trimmed_status(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.04,
            "entry_price": 100.0,
            "current_price": 106.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        assert pos["trim_status"] == "half_trimmed"

    def test_sets_trail_stop_level(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.04,
            "entry_price": 100.0,
            "current_price": 106.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        # With 2.5% method, trail = peak * (1 - 0.025) = 106 * 0.975 = 103.35
        assert pos["trail_stop_level"] == pytest.approx(106.0 * 0.975)

    def test_restores_cash(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.04,
            "entry_price": 100.0,
            "current_price": 106.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        # Cash restored by original_size (0.04) — half of 2x pair size
        assert book["cash_pct"] == pytest.approx(0.94)

    def test_logs_trade_journal(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.04,
            "entry_price": 100.0,
            "current_price": 106.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        assert len(book["trade_journal"]) == 1
        entry = book["trade_journal"][0]
        assert entry["action"] == "trim"
        assert entry["ticker"] == "XOM"
        assert entry["reason"] == "take_profit_trim"
        # With 2.5% method: trail = 106 * 0.975 = 103.35
        assert entry["trail_stop_level"] == pytest.approx(106.0 * 0.975)

    def test_short_position_trim(self):
        pos = {
            "ticker": "AAPL",
            "direction": "short",
            "trim_status": "untrimmed",
            "size_pct_nav": 0.03,
            "entry_price": 100.0,
            "current_price": 94.0,
            "combined_pnl_pct": 0.06,
            "take_profit": "5%",
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trim(pos, book)

        assert pos["size_pct_nav"] == pytest.approx(0.015)
        assert pos["trim_status"] == "half_trimmed"
        # With 2.5% method for short: trail = peak * (1 + 0.025) = 94 * 1.025 = 96.35
        assert pos["trail_stop_level"] == pytest.approx(94.0 * 1.025)


# ---------------------------------------------------------------------------
# execute_trail_stop_close tests
# ---------------------------------------------------------------------------


class TestExecuteTrailStopClose:
    def test_closes_position(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "size_pct_nav": 0.02,
            "current_price": 102.0,
            "combined_pnl_pct": 0.02,
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trail_stop_close(pos, book)

        assert pos["status"] == "closed"
        assert pos["exit_reason"] == "trail_stop_auto"
        assert pos["trim_status"] == "fully_exited"

    def test_restores_cash(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "size_pct_nav": 0.02,
            "current_price": 102.0,
            "combined_pnl_pct": 0.02,
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trail_stop_close(pos, book)

        # Cash restored by 2 × size_pct_nav = 2 × 0.02 = 0.04
        assert book["cash_pct"] == pytest.approx(0.94)

    def test_exit_price_is_slippage_adjusted(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "size_pct_nav": 0.02,
            "current_price": 102.0,
            "combined_pnl_pct": 0.02,
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trail_stop_close(pos, book)

        # Long exit: price × (1 - 5/10000) = 102 × 0.9995 = 101.949
        assert pos["exit_price"] == pytest.approx(102.0 * 0.9995)

    def test_logs_trade_journal(self):
        pos = {
            "ticker": "XOM",
            "direction": "long",
            "trim_status": "half_trimmed",
            "trail_stop_level": 103.0,
            "size_pct_nav": 0.02,
            "current_price": 102.0,
            "combined_pnl_pct": 0.02,
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trail_stop_close(pos, book)

        assert len(book["trade_journal"]) == 1
        entry = book["trade_journal"][0]
        assert entry["action"] == "close"
        assert entry["exit_reason"] == "trail_stop_auto"

    def test_short_position_trail_stop(self):
        pos = {
            "ticker": "AAPL",
            "direction": "short",
            "trim_status": "half_trimmed",
            "trail_stop_level": 97.0,
            "size_pct_nav": 0.02,
            "current_price": 98.0,
            "combined_pnl_pct": 0.01,
        }
        book = {"cash_pct": 0.90, "trade_journal": []}

        execute_trail_stop_close(pos, book)

        assert pos["status"] == "closed"
        assert pos["exit_reason"] == "trail_stop_auto"
        # Short exit: price × (1 + 5/10000) = 98 × 1.0005 = 98.049
        assert pos["exit_price"] == pytest.approx(98.0 * 1.0005)


# ---------------------------------------------------------------------------
# process_take_profit_and_trail_stops integration tests
# ---------------------------------------------------------------------------


class TestProcessTakeProfitAndTrailStops:
    def test_trims_eligible_position(self):
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
                    "current_price": 106.0,
                    "combined_pnl_pct": 0.06,
                    "take_profit": "5%",
                }
            ],
        }

        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)

        assert trim_count == 1
        assert trail_close_count == 0
        assert book["positions"][0]["trim_status"] == "half_trimmed"

    def test_trail_stop_closes_eligible_position(self):
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "active",
                    "trim_status": "half_trimmed",
                    "trail_stop_level": 103.0,
                    "size_pct_nav": 0.02,
                    "current_price": 101.0,
                    "combined_pnl_pct": 0.01,
                }
            ],
        }

        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)

        assert trim_count == 0
        assert trail_close_count == 1
        assert book["positions"][0]["status"] == "closed"

    def test_skips_closed_positions(self):
        book = {
            "cash_pct": 0.90,
            "trade_journal": [],
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "status": "closed",
                    "trim_status": "untrimmed",
                    "size_pct_nav": 0.04,
                    "entry_price": 100.0,
                    "current_price": 110.0,
                    "combined_pnl_pct": 0.10,
                    "take_profit": "5%",
                }
            ],
        }

        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)

        assert trim_count == 0
        assert trail_close_count == 0

    def test_no_action_when_below_target(self):
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
                    "current_price": 103.0,
                    "combined_pnl_pct": 0.03,
                    "take_profit": "5%",
                }
            ],
        }

        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)

        assert trim_count == 0
        assert trail_close_count == 0
        assert book["positions"][0]["trim_status"] == "untrimmed"
