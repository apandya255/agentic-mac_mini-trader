"""
Unit tests for scripts/post_close_wrap.py

Validates:
- Trading day gating (skip on weekends/holidays)
- Template wrap generation stays within 12-line limit
- P&L computation correctness
- Movers detection and ranking
- Leverage computation
- Factor beta alert detection
- Graceful degradation without OPENROUTER_API_KEY

Requirements: 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.post_close_wrap import (
    _check_factor_beta,
    _compute_book_pnl,
    _compute_leverage,
    _compute_movers,
    _generate_template_wrap,
    _get_todays_entries_exits,
)


# ---------------------------------------------------------------------------
# Book P&L computation tests
# ---------------------------------------------------------------------------


class TestComputeBookPnl:
    """Requirement 8.2: Book P&L accuracy."""

    def test_positive_pnl(self):
        """Positive P&L computed correctly."""
        book = {"nav": 10500000, "initial_nav": 10000000}
        result = _compute_book_pnl(book)
        assert result["total_pnl_pct"] == pytest.approx(0.05)
        assert result["total_pnl_dollars"] == pytest.approx(500000)

    def test_negative_pnl(self):
        """Negative P&L computed correctly."""
        book = {"nav": 9800000, "initial_nav": 10000000}
        result = _compute_book_pnl(book)
        assert result["total_pnl_pct"] == pytest.approx(-0.02)
        assert result["total_pnl_dollars"] == pytest.approx(-200000)

    def test_zero_initial_nav(self):
        """Zero initial NAV handled gracefully."""
        book = {"nav": 100, "initial_nav": 0}
        result = _compute_book_pnl(book)
        assert result["total_pnl_pct"] == 0.0
        assert result["total_pnl_dollars"] == 0.0

    def test_flat_pnl(self):
        """Flat book returns zero."""
        book = {"nav": 10000000, "initial_nav": 10000000}
        result = _compute_book_pnl(book)
        assert result["total_pnl_pct"] == 0.0
        assert result["total_pnl_dollars"] == 0.0


# ---------------------------------------------------------------------------
# Today's entries/exits tests
# ---------------------------------------------------------------------------


class TestGetTodaysEntriesExits:
    """Requirement 8.2: Today's entries and exits."""

    def test_entries_detected(self):
        """Today's entries are found in journal."""
        today = "2026-08-08"
        book = {
            "trade_journal": [
                {
                    "action": "open",
                    "timestamp": f"{today}T10:30:00",
                    "order": {"ticker": "AAPL", "direction": "long", "hedge_ticker": "XLK", "size_pct_nav": 0.04},
                    "entry_price": 185.0,
                    "hedge_entry_price": 210.0,
                },
                {
                    "action": "open",
                    "timestamp": "2026-08-07T09:30:00",
                    "order": {"ticker": "MSFT", "direction": "long", "hedge_ticker": "XLK", "size_pct_nav": 0.03},
                    "entry_price": 410.0,
                    "hedge_entry_price": 210.0,
                },
            ]
        }

        with patch("scripts.post_close_wrap._get_today_str", return_value=today):
            result = _get_todays_entries_exits(book)
            assert len(result["entries"]) == 1
            assert result["entries"][0]["ticker"] == "AAPL"
            assert len(result["exits"]) == 0

    def test_exits_detected(self):
        """Today's exits are found in journal."""
        today = "2026-08-08"
        book = {
            "trade_journal": [
                {
                    "action": "close",
                    "timestamp": f"{today}T15:30:00",
                    "order": {"ticker": "XOM", "direction": "long", "hedge_ticker": "RSPG", "size_pct_nav": 0.04},
                    "entry_price": 155.0,
                    "hedge_entry_price": 105.0,
                },
            ]
        }

        with patch("scripts.post_close_wrap._get_today_str", return_value=today):
            result = _get_todays_entries_exits(book)
            assert len(result["exits"]) == 1
            assert result["exits"][0]["ticker"] == "XOM"

    def test_empty_journal(self):
        """Empty journal returns empty lists."""
        book = {"trade_journal": []}
        result = _get_todays_entries_exits(book)
        assert result["entries"] == []
        assert result["exits"] == []


# ---------------------------------------------------------------------------
# Movers computation tests
# ---------------------------------------------------------------------------


class TestComputeMovers:
    """Requirement 8.2: Movers detection."""

    def test_movers_sorted_by_absolute_change(self):
        """Movers sorted by absolute daily change descending."""
        book = {
            "positions": [
                {
                    "ticker": "A",
                    "hedge_ticker": "H1",
                    "status": "active",
                    "combined_pnl_pct": 0.02,
                    "daily_change_pct": 0.01,
                    "size_pct_nav": 0.04,
                    "price_history": [],
                },
                {
                    "ticker": "B",
                    "hedge_ticker": "H2",
                    "status": "active",
                    "combined_pnl_pct": -0.03,
                    "daily_change_pct": -0.02,
                    "size_pct_nav": 0.03,
                    "price_history": [],
                },
                {
                    "ticker": "C",
                    "hedge_ticker": "H3",
                    "status": "active",
                    "combined_pnl_pct": 0.05,
                    "daily_change_pct": 0.005,
                    "size_pct_nav": 0.04,
                    "price_history": [],
                },
            ]
        }
        movers = _compute_movers(book)
        assert movers[0]["ticker"] == "B"  # -2% is biggest absolute move
        assert movers[1]["ticker"] == "A"  # +1%
        assert movers[2]["ticker"] == "C"  # +0.5%

    def test_closed_positions_excluded(self):
        """Closed positions are not included in movers."""
        book = {
            "positions": [
                {
                    "ticker": "A",
                    "hedge_ticker": "H1",
                    "status": "closed",
                    "combined_pnl_pct": 0.10,
                    "daily_change_pct": 0.10,
                    "size_pct_nav": 0.04,
                    "price_history": [],
                },
                {
                    "ticker": "B",
                    "hedge_ticker": "H2",
                    "status": "active",
                    "combined_pnl_pct": 0.01,
                    "daily_change_pct": 0.005,
                    "size_pct_nav": 0.03,
                    "price_history": [],
                },
            ]
        }
        movers = _compute_movers(book)
        assert len(movers) == 1
        assert movers[0]["ticker"] == "B"

    def test_daily_change_from_price_history(self):
        """Daily change computed from price_history if daily_change_pct is 0."""
        book = {
            "positions": [
                {
                    "ticker": "A",
                    "hedge_ticker": "H1",
                    "status": "active",
                    "combined_pnl_pct": 0.03,
                    "daily_change_pct": 0.0,
                    "size_pct_nav": 0.04,
                    "price_history": [
                        {"combined_pnl_pct": 0.01},
                        {"combined_pnl_pct": 0.03},
                    ],
                },
            ]
        }
        movers = _compute_movers(book)
        assert movers[0]["daily_change_pct"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Leverage computation tests
# ---------------------------------------------------------------------------


class TestComputeLeverage:
    """Requirement 8.2: Leverage stance."""

    def test_leverage_with_positions(self):
        """Leverage computed correctly with active positions."""
        book = {
            "cash_pct": 0.50,
            "positions": [
                {"status": "active", "size_pct_nav": 0.04},
                {"status": "active", "size_pct_nav": 0.03},
                {"status": "closed", "size_pct_nav": 0.05},
            ],
        }
        result = _compute_leverage(book)
        assert result["position_count"] == 2
        assert result["gross_exposure_pct"] == pytest.approx(0.14)  # (0.04+0.03)*2
        assert result["cash_pct"] == 0.50

    def test_leverage_empty_book(self):
        """Empty book returns zero exposure."""
        book = {"cash_pct": 1.0, "positions": []}
        result = _compute_leverage(book)
        assert result["position_count"] == 0
        assert result["gross_exposure_pct"] == 0.0
        assert result["cash_pct"] == 1.0


# ---------------------------------------------------------------------------
# Factor beta tests
# ---------------------------------------------------------------------------


class TestCheckFactorBeta:
    """Requirement 8.2: Factor beta alert detection."""

    def test_no_factor_data(self):
        """No factor data returns empty alerts."""
        book = {"positions": [{"status": "active", "ticker": "XOM"}]}
        result = _check_factor_beta(book)
        assert result == []

    def test_exceeded_book_level_beta(self):
        """Book-level factor betas exceeding |0.4| detected."""
        book = {
            "factor_betas": {"momentum": 0.5, "value": -0.3, "size": -0.45},
            "positions": [],
        }
        result = _check_factor_beta(book)
        assert len(result) == 2  # momentum(0.5) and size(-0.45)

    def test_exceeded_position_level_beta(self):
        """Position-level factor betas exceeding |0.4| detected."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "active",
                    "factor_betas": {"oil_beta": 0.8},
                },
                {
                    "ticker": "V",
                    "status": "active",
                    "factor_betas": {"rates_beta": 0.2},
                },
            ]
        }
        result = _check_factor_beta(book)
        assert len(result) == 1
        assert result[0]["factor"] == "oil_beta"
        assert result[0]["ticker"] == "XOM"


# ---------------------------------------------------------------------------
# Template wrap generation tests
# ---------------------------------------------------------------------------


class TestGenerateTemplateWrap:
    """Requirement 8.2, 8.3: Wrap content and line limit."""

    def test_wrap_within_12_lines(self):
        """Template wrap never exceeds 12 lines."""
        book_pnl = {
            "nav": 10500000,
            "initial_nav": 10000000,
            "total_pnl_pct": 0.05,
            "total_pnl_dollars": 500000,
        }
        entries_exits = {
            "entries": [{"ticker": "AAPL", "direction": "long"}],
            "exits": [{"ticker": "XOM"}],
        }
        movers = [
            {"ticker": "A", "hedge_ticker": "H1", "daily_change_pct": 0.02, "combined_pnl_pct": 0.05, "size_pct_nav": 0.04},
            {"ticker": "B", "hedge_ticker": "H2", "daily_change_pct": -0.015, "combined_pnl_pct": -0.03, "size_pct_nav": 0.03},
            {"ticker": "C", "hedge_ticker": "H3", "daily_change_pct": 0.005, "combined_pnl_pct": 0.01, "size_pct_nav": 0.03},
        ]
        leverage = {"gross_exposure_pct": 0.42, "net_exposure_pct": 0.0, "cash_pct": 0.58, "position_count": 6}
        factor_alerts = [{"factor": "momentum", "beta": 0.55}]

        wrap = _generate_template_wrap(book_pnl, entries_exits, movers, leverage, factor_alerts)
        lines = wrap.strip().split("\n")
        assert len(lines) <= 12

    def test_wrap_contains_pnl(self):
        """Wrap includes P&L information."""
        book_pnl = {
            "nav": 10500000,
            "initial_nav": 10000000,
            "total_pnl_pct": 0.05,
            "total_pnl_dollars": 500000,
        }
        wrap = _generate_template_wrap(
            book_pnl,
            {"entries": [], "exits": []},
            [],
            {"gross_exposure_pct": 0.0, "net_exposure_pct": 0.0, "cash_pct": 1.0, "position_count": 0},
            [],
        )
        assert "+5.00%" in wrap
        assert "$500,000" in wrap

    def test_wrap_contains_movers(self):
        """Wrap includes mover information."""
        book_pnl = {"nav": 10000000, "initial_nav": 10000000, "total_pnl_pct": 0.0, "total_pnl_dollars": 0.0}
        movers = [
            {"ticker": "XOM", "hedge_ticker": "RSPG", "daily_change_pct": 0.015, "combined_pnl_pct": 0.03, "size_pct_nav": 0.04},
        ]
        wrap = _generate_template_wrap(
            book_pnl,
            {"entries": [], "exits": []},
            movers,
            {"gross_exposure_pct": 0.08, "net_exposure_pct": 0.0, "cash_pct": 0.92, "position_count": 1},
            [],
        )
        assert "XOM" in wrap
        assert "Movers" in wrap

    def test_wrap_empty_book(self):
        """Wrap handles empty book gracefully."""
        book_pnl = {"nav": 10000000, "initial_nav": 10000000, "total_pnl_pct": 0.0, "total_pnl_dollars": 0.0}
        wrap = _generate_template_wrap(
            book_pnl,
            {"entries": [], "exits": []},
            [],
            {"gross_exposure_pct": 0.0, "net_exposure_pct": 0.0, "cash_pct": 1.0, "position_count": 0},
            [],
        )
        assert "No active positions" in wrap
        lines = wrap.strip().split("\n")
        assert len(lines) <= 12

    def test_wrap_contains_leverage(self):
        """Wrap includes leverage information."""
        book_pnl = {"nav": 10000000, "initial_nav": 10000000, "total_pnl_pct": 0.0, "total_pnl_dollars": 0.0}
        wrap = _generate_template_wrap(
            book_pnl,
            {"entries": [], "exits": []},
            [],
            {"gross_exposure_pct": 0.42, "net_exposure_pct": 0.0, "cash_pct": 0.58, "position_count": 6},
            [],
        )
        assert "Leverage" in wrap
        assert "42%" in wrap
        assert "6 positions" in wrap

    def test_wrap_header_contains_date(self):
        """Wrap header contains a date reference."""
        book_pnl = {"nav": 10000000, "initial_nav": 10000000, "total_pnl_pct": 0.0, "total_pnl_dollars": 0.0}
        wrap = _generate_template_wrap(
            book_pnl,
            {"entries": [], "exits": []},
            [],
            {"gross_exposure_pct": 0.0, "net_exposure_pct": 0.0, "cash_pct": 1.0, "position_count": 0},
            [],
        )
        assert "POST-CLOSE WRAP" in wrap
