"""
Unit tests for trail breach detection and auto-execution in price_poller.py.

Tests the handle_trail_breaches function and its sub-components:
- Position closure logic
- Cash allocation restoration
- Exit details computation
- Journal and lessons entry writing
- Positions file sync
- NAV snapshot recording

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 20.1, 20.2, 20.3, 20.4
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Import the price_poller module
import importlib.util

spec = importlib.util.spec_from_file_location(
    "price_poller", os.path.join(PROJECT_ROOT, "scripts", "price_poller.py")
)
price_poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(price_poller)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_book():
    """A sample book with one active position that has breached the trail."""
    return {
        "nav": 10000000,
        "initial_nav": 10000000,
        "cash_pct": 0.96,
        "positions": [
            {
                "ticker": "XOM",
                "direction": "long",
                "hedge_ticker": "RSPG",
                "hedge_direction": "short",
                "pair_ratio": 1.4788,
                "size_pct_nav": 0.04,
                "conviction": 8,
                "entry_price": 154.77,
                "hedge_entry_price": 104.66,
                "current_price": 150.00,
                "hedge_current_price": 106.00,
                "entry_date": "2026-07-28",
                "status": "active",
                "combined_pnl_pct": -0.03,  # -3%: breach from peak of 0.0
                "peak_pnl": 0.0,
                "unrealized_pnl_pct": -0.0308,
                "hedge_unrealized_pnl_pct": -0.0128,
            }
        ],
        "trade_journal": [],
    }


@pytest.fixture
def non_breached_book():
    """A sample book with a position that has NOT breached the trail."""
    return {
        "nav": 10000000,
        "initial_nav": 10000000,
        "cash_pct": 0.96,
        "positions": [
            {
                "ticker": "WMT",
                "direction": "long",
                "hedge_ticker": "RSPS",
                "hedge_direction": "short",
                "pair_ratio": 3.59,
                "size_pct_nav": 0.03,
                "conviction": 7,
                "entry_price": 113.54,
                "hedge_entry_price": 31.62,
                "current_price": 114.00,
                "hedge_current_price": 31.50,
                "entry_date": "2026-07-28",
                "status": "active",
                "combined_pnl_pct": 0.004,  # +0.4%, well within trail
                "peak_pnl": 0.008,
                "unrealized_pnl_pct": 0.004,
                "hedge_unrealized_pnl_pct": 0.004,
            }
        ],
        "trade_journal": [],
    }


@pytest.fixture
def temp_desk_files(tmp_path):
    """Create temporary desk files and patch the module paths."""
    journal = tmp_path / "journal.md"
    lessons = tmp_path / "lessons.md"
    positions = tmp_path / "positions.md"
    pnl_history = tmp_path / "pnl_history.json"

    # Write initial content
    journal.write_text("# Trade Journal\n\n")
    lessons.write_text("# Process Lessons\n\n| — lessons begin below — |\n")
    positions.write_text("# Positions\n")
    pnl_history.write_text("[]")

    return {
        "journal": journal,
        "lessons": lessons,
        "positions": positions,
        "pnl_history": pnl_history,
    }


# ---------------------------------------------------------------------------
# Test: _compute_exit_details
# ---------------------------------------------------------------------------


class TestComputeExitDetails:
    def test_basic_exit_computation(self):
        """Exit details correctly compute days held, slippage, and ratios."""
        pos = {
            "ticker": "XOM",
            "hedge_ticker": "RSPG",
            "direction": "long",
            "entry_price": 154.77,
            "hedge_entry_price": 104.66,
            "current_price": 150.00,
            "hedge_current_price": 106.00,
            "entry_date": "2026-07-28",
            "status": "active",
            "combined_pnl_pct": -0.03,
            "peak_pnl": 0.0,
            "size_pct_nav": 0.04,
        }

        details = price_poller._compute_exit_details(pos)

        assert details["ticker_fill"] == 150.00
        assert details["hedge_fill"] == 106.00
        assert details["pnl_pct"] == -0.03
        assert details["peak_pnl"] == 0.0
        assert details["size_pct"] == 0.04
        # Exit ratio = 150 / 106 ≈ 1.4151
        assert abs(details["exit_ratio"] - 1.4151) < 0.001
        # Entry ratio = 154.77 / 104.66 ≈ 1.4787
        assert abs(details["entry_ratio"] - 1.4787) < 0.001
        # Stop level = peak - 0.025 = -0.025
        assert abs(details["stop_level_pnl"] - (-0.025)) < 0.0001
        # Trail slippage = stop_level - combined = -0.025 - (-0.03) = 0.005
        assert abs(details["trail_slippage"] - 0.005) < 0.0001
        assert details["days_held"] >= 0

    def test_peak_above_zero(self):
        """When peak is positive, stop level is higher."""
        pos = {
            "ticker": "V",
            "hedge_ticker": "RSPF",
            "direction": "long",
            "entry_price": 368.79,
            "hedge_entry_price": 84.58,
            "current_price": 360.00,
            "hedge_current_price": 85.00,
            "entry_date": "2026-08-01",
            "status": "active",
            "combined_pnl_pct": 0.02,  # +2%
            "peak_pnl": 0.05,  # Peak was +5%
            "size_pct_nav": 0.04,
        }

        details = price_poller._compute_exit_details(pos)

        # Stop level = 0.05 - 0.025 = 0.025
        assert abs(details["stop_level_pnl"] - 0.025) < 0.0001
        # Trail slippage = 0.025 - 0.02 = 0.005 (exited 0.5% worse than stop)
        assert abs(details["trail_slippage"] - 0.005) < 0.0001


# ---------------------------------------------------------------------------
# Test: _close_position_in_book
# ---------------------------------------------------------------------------


class TestClosePositionInBook:
    def test_position_status_set_to_closed(self, sample_book):
        """Position status changes to 'closed' on trail breach."""
        pos = sample_book["positions"][0]
        book = price_poller._close_position_in_book(sample_book, pos)

        assert pos["status"] == "closed"
        assert "exit_date" in pos
        assert pos["exit_price"] == 150.00
        assert pos["hedge_exit_price"] == 106.00

    def test_cash_allocation_restored(self, sample_book):
        """Cash percentage increases by the position's size_pct_nav."""
        initial_cash = sample_book["cash_pct"]
        pos = sample_book["positions"][0]
        size = pos["size_pct_nav"]

        book = price_poller._close_position_in_book(sample_book, pos)

        assert book["cash_pct"] == initial_cash + size

    def test_trade_journal_entry_added(self, sample_book):
        """A close entry is appended to the trade_journal."""
        pos = sample_book["positions"][0]
        book = price_poller._close_position_in_book(sample_book, pos)

        assert len(book["trade_journal"]) == 1
        entry = book["trade_journal"][0]
        assert entry["action"] == "close"
        assert entry["reason"] == "trail_breach"
        assert entry["ticker"] == "XOM"
        assert entry["hedge_ticker"] == "RSPG"


# ---------------------------------------------------------------------------
# Test: handle_trail_breaches (integration)
# ---------------------------------------------------------------------------


class TestHandleTrailBreaches:
    def test_breached_position_gets_closed(self, sample_book, temp_desk_files):
        """A position that has breached the trail is closed."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            result_book = price_poller.handle_trail_breaches(sample_book)

        # Position should be closed
        pos = result_book["positions"][0]
        assert pos["status"] == "closed"

        # Cash should be restored
        assert result_book["cash_pct"] == 1.0  # 0.96 + 0.04

    def test_non_breached_position_remains_active(self, non_breached_book, temp_desk_files):
        """A position within its trail stays active."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            result_book = price_poller.handle_trail_breaches(non_breached_book)

        # Position should remain active
        pos = result_book["positions"][0]
        assert pos["status"] == "active"
        # Cash unchanged
        assert result_book["cash_pct"] == 0.96

    def test_journal_entry_written_on_breach(self, sample_book, temp_desk_files):
        """A journal entry is appended to the journal file on breach."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            price_poller.handle_trail_breaches(sample_book)

        content = temp_desk_files["journal"].read_text()
        assert "CLOSE (trail breach)" in content
        assert "XOM" in content
        assert "RSPG" in content

    def test_lessons_entry_written_on_breach(self, sample_book, temp_desk_files):
        """A lessons entry is appended to the lessons file on breach."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            price_poller.handle_trail_breaches(sample_book)

        content = temp_desk_files["lessons"].read_text()
        assert "XOM" in content
        assert "Trail stop enforced" in content

    def test_positions_file_synced_on_breach(self, sample_book, temp_desk_files):
        """desk/positions.md is rewritten to reflect closed position."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            price_poller.handle_trail_breaches(sample_book)

        content = temp_desk_files["positions"].read_text()
        assert "CLOSED" in content
        assert "XOM/RSPG" in content

    def test_pnl_history_updated_on_breach(self, sample_book, temp_desk_files):
        """memos/state/pnl_history.json gets a new snapshot on breach."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True),
        ):
            price_poller.handle_trail_breaches(sample_book)

        history = json.loads(temp_desk_files["pnl_history"].read_text())
        assert len(history) == 1
        assert "nav" in history[0]
        assert "timestamp" in history[0]

    def test_telegram_alert_sent_on_breach(self, sample_book, temp_desk_files):
        """A Telegram alert is queued/sent when a trail breach executes."""
        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True) as mock_tg,
        ):
            price_poller.handle_trail_breaches(sample_book)

        mock_tg.assert_called_once()
        call_args = mock_tg.call_args[0][0]
        assert "Trail Breach" in call_args
        assert "XOM" in call_args
        assert "RSPG" in call_args

    def test_multiple_breaches_handled(self, temp_desk_files):
        """Multiple positions breaching are all closed in one pass."""
        book = {
            "nav": 10000000,
            "initial_nav": 10000000,
            "cash_pct": 0.90,
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "hedge_ticker": "RSPG",
                    "hedge_direction": "short",
                    "entry_price": 154.77,
                    "hedge_entry_price": 104.66,
                    "current_price": 150.00,
                    "hedge_current_price": 108.00,
                    "entry_date": "2026-07-28",
                    "status": "active",
                    "combined_pnl_pct": -0.03,
                    "peak_pnl": 0.0,
                    "size_pct_nav": 0.04,
                },
                {
                    "ticker": "NFLX",
                    "direction": "long",
                    "hedge_ticker": "RSPC",
                    "hedge_direction": "short",
                    "entry_price": 73.38,
                    "hedge_entry_price": 36.19,
                    "current_price": 70.00,
                    "hedge_current_price": 37.00,
                    "entry_date": "2026-07-28",
                    "status": "active",
                    "combined_pnl_pct": -0.034,
                    "peak_pnl": 0.0,
                    "size_pct_nav": 0.03,
                },
                {
                    "ticker": "WMT",
                    "direction": "long",
                    "hedge_ticker": "RSPS",
                    "hedge_direction": "short",
                    "entry_price": 113.54,
                    "hedge_entry_price": 31.62,
                    "current_price": 114.00,
                    "hedge_current_price": 31.50,
                    "entry_date": "2026-07-28",
                    "status": "active",
                    "combined_pnl_pct": 0.004,
                    "peak_pnl": 0.008,
                    "size_pct_nav": 0.03,
                },
            ],
            "trade_journal": [],
        }

        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True) as mock_tg,
        ):
            result_book = price_poller.handle_trail_breaches(book)

        # XOM and NFLX should be closed, WMT stays active
        assert result_book["positions"][0]["status"] == "closed"
        assert result_book["positions"][1]["status"] == "closed"
        assert result_book["positions"][2]["status"] == "active"

        # Cash restored for both closed positions (0.90 + 0.04 + 0.03 = 0.97)
        assert abs(result_book["cash_pct"] - 0.97) < 0.001

        # Telegram called twice (once per breach)
        assert mock_tg.call_count == 2

    def test_already_closed_positions_skipped(self, temp_desk_files):
        """Positions with status != 'active' are not checked for breach."""
        book = {
            "nav": 10000000,
            "initial_nav": 10000000,
            "cash_pct": 1.0,
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "hedge_ticker": "RSPG",
                    "hedge_direction": "short",
                    "entry_price": 154.77,
                    "hedge_entry_price": 104.66,
                    "current_price": 150.00,
                    "hedge_current_price": 108.00,
                    "entry_date": "2026-07-28",
                    "status": "closed",  # Already closed
                    "combined_pnl_pct": -0.05,
                    "peak_pnl": 0.0,
                    "size_pct_nav": 0.04,
                },
            ],
            "trade_journal": [],
        }

        with (
            patch.object(price_poller, "JOURNAL_PATH", temp_desk_files["journal"]),
            patch.object(price_poller, "LESSONS_PATH", temp_desk_files["lessons"]),
            patch.object(price_poller, "POSITIONS_PATH", temp_desk_files["positions"]),
            patch.object(price_poller, "PNL_HISTORY_PATH", temp_desk_files["pnl_history"]),
            patch.object(price_poller, "send_telegram", return_value=True) as mock_tg,
        ):
            result_book = price_poller.handle_trail_breaches(book)

        # Nothing should change
        assert result_book["cash_pct"] == 1.0
        mock_tg.assert_not_called()
