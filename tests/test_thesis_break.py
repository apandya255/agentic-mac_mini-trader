"""
Unit tests for thesis-break detection in monitor.py.

Tests parse_holding_period() and check_thesis_break() functions.

**Validates: Requirements 5.1, 5.2, 5.3**
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitor import parse_holding_period, check_thesis_break


# ──────────────────────────────────────────────────────────────────────────────
# parse_holding_period tests
# ──────────────────────────────────────────────────────────────────────────────


class TestParseHoldingPeriod:
    """Tests for parse_holding_period()."""

    def test_plain_days(self):
        assert parse_holding_period("30 days") == 30

    def test_trading_days(self):
        assert parse_holding_period("20 trading days") == 20

    def test_single_day(self):
        assert parse_holding_period("1 day") == 1

    def test_weeks(self):
        assert parse_holding_period("4 weeks") == 28

    def test_single_week(self):
        assert parse_holding_period("1 week") == 7

    def test_range_weeks_uses_upper_bound(self):
        assert parse_holding_period("2-3 weeks") == 21

    def test_range_weeks_1_2(self):
        assert parse_holding_period("1-2 weeks") == 14

    def test_months(self):
        assert parse_holding_period("2 months") == 60

    def test_single_month(self):
        assert parse_holding_period("1 month") == 30

    def test_range_months(self):
        assert parse_holding_period("1-2 months") == 60

    def test_unparseable_defaults_to_60(self):
        assert parse_holding_period("sometime soon") == 60

    def test_empty_string_defaults_to_60(self):
        assert parse_holding_period("") == 60

    def test_none_defaults_to_60(self):
        # The function receives None when field is missing
        assert parse_holding_period(None) == 60

    def test_60_days(self):
        assert parse_holding_period("60 days") == 60

    def test_case_insensitive(self):
        assert parse_holding_period("2 Weeks") == 14


# ──────────────────────────────────────────────────────────────────────────────
# check_thesis_break tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCheckThesisBreak:
    """Tests for check_thesis_break()."""

    def test_not_overdue_returns_none(self):
        """Position within holding period should return None."""
        today = date(2024, 6, 1)
        pos = {
            "entry_date": "2024-05-15",
            "expected_holding_period": "30 days",
            "thesis_status": "active",
        }
        assert check_thesis_break(pos, today) is None

    def test_overdue_not_flagged_returns_flag_overdue(self):
        """Position past holding period that hasn't been flagged yet."""
        today = date(2024, 6, 20)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "active",
        }
        # 50 days held > 30 expected → flag_overdue
        assert check_thesis_break(pos, today) == "flag_overdue"

    def test_overdue_already_flagged_positive_pnl_returns_none(self):
        """Flagged overdue but positive P&L should not close."""
        today = date(2024, 6, 20)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": 0.02,  # positive
        }
        assert check_thesis_break(pos, today) is None

    def test_overdue_negative_pnl_within_5_days_returns_none(self):
        """Flagged overdue, negative P&L, but fewer than 5 days overdue — don't close."""
        today = date(2024, 6, 8)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": -0.02,
        }
        # Only 3 days overdue (not > 5)
        assert check_thesis_break(pos, today) is None

    def test_overdue_negative_pnl_over_5_days_returns_close(self):
        """Flagged overdue + negative P&L + > 5 days = close."""
        today = date(2024, 6, 15)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": -0.01,
        }
        # 10 days since flagged > 5 and negative P&L
        assert check_thesis_break(pos, today) == "close"

    def test_exactly_5_days_overdue_returns_none(self):
        """Exactly 5 days overdue should NOT close (must be > 5)."""
        today = date(2024, 6, 10)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": -0.01,
        }
        # Exactly 5 days overdue
        assert check_thesis_break(pos, today) is None

    def test_6_days_overdue_with_negative_pnl_closes(self):
        """6 days overdue with negative P&L = close."""
        today = date(2024, 6, 11)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": -0.005,
        }
        assert check_thesis_break(pos, today) == "close"

    def test_no_entry_date_returns_none(self):
        """Position without entry_date should return None."""
        pos = {
            "expected_holding_period": "30 days",
            "thesis_status": "active",
        }
        assert check_thesis_break(pos, date.today()) is None

    def test_missing_overdue_since_returns_none(self):
        """review_overdue but no overdue_since should return None."""
        today = date(2024, 6, 20)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            # overdue_since is missing
            "combined_pnl_pct": -0.02,
        }
        assert check_thesis_break(pos, today) is None

    def test_zero_pnl_not_negative_returns_none(self):
        """Zero P&L should not trigger close (must be < 0)."""
        today = date(2024, 6, 15)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "review_overdue",
            "overdue_since": "2024-06-05",
            "combined_pnl_pct": 0.0,
        }
        assert check_thesis_break(pos, today) is None

    def test_weeks_holding_period(self):
        """Test with weeks-based holding period."""
        today = date(2024, 6, 1)
        pos = {
            "entry_date": "2024-04-01",
            "expected_holding_period": "2-3 weeks",
            "thesis_status": "active",
        }
        # 61 days held > 21 expected → flag_overdue
        assert check_thesis_break(pos, today) == "flag_overdue"

    def test_on_boundary_day_returns_none(self):
        """Position held exactly the expected period should not be flagged."""
        today = date(2024, 5, 31)
        pos = {
            "entry_date": "2024-05-01",
            "expected_holding_period": "30 days",
            "thesis_status": "active",
        }
        # 30 days held == 30 expected → not overdue
        assert check_thesis_break(pos, today) is None


# ──────────────────────────────────────────────────────────────────────────────
# check_thesis_break — review_date tests (Requirements 9.1, 9.2, 9.3)
# ──────────────────────────────────────────────────────────────────────────────


class TestCheckThesisBreakReviewDate:
    """Tests for review_date trigger path in check_thesis_break()."""

    def test_past_review_date_flags_overdue(self):
        """Position past review_date with thesis_status != 'reviewed' → flag_overdue."""
        today = date(2025, 6, 15)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "active",
        }
        # review_date exceeded, holding period NOT exceeded, should still flag
        assert check_thesis_break(pos, today) == "flag_overdue"

    def test_past_review_date_with_reviewed_status_no_flag(self):
        """Position past review_date but thesis_status='reviewed' → None."""
        today = date(2025, 6, 15)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "reviewed",
        }
        assert check_thesis_break(pos, today) is None

    def test_review_date_not_yet_exceeded(self):
        """Position where review_date is in the future → None."""
        today = date(2025, 5, 28)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "active",
        }
        assert check_thesis_break(pos, today) is None

    def test_review_date_exactly_today_no_flag(self):
        """Position where review_date == today → None (must be exceeded, not equal)."""
        today = date(2025, 6, 1)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "active",
        }
        assert check_thesis_break(pos, today) is None

    def test_review_date_already_overdue_goes_to_close_check(self):
        """Position past review_date already flagged review_overdue → falls through to close logic."""
        today = date(2025, 6, 20)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "review_overdue",
            "overdue_since": "2025-06-02",
            "combined_pnl_pct": -0.01,
        }
        # 18 days overdue with negative P&L → close
        assert check_thesis_break(pos, today) == "close"

    def test_review_date_overdue_positive_pnl_no_close(self):
        """Position review_overdue with positive P&L → None (no close)."""
        today = date(2025, 6, 20)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "2025-06-01",
            "thesis_status": "review_overdue",
            "overdue_since": "2025-06-02",
            "combined_pnl_pct": 0.02,
        }
        assert check_thesis_break(pos, today) is None

    def test_review_date_invalid_format_ignored(self):
        """Position with invalid review_date → falls through to holding period logic."""
        today = date(2025, 6, 15)
        pos = {
            "entry_date": "2025-05-01",
            "expected_holding_period": "60 days",
            "review_date": "invalid-date",
            "thesis_status": "active",
        }
        # Invalid review_date ignored, holding period (60 days) not exceeded → None
        assert check_thesis_break(pos, today) is None


# ──────────────────────────────────────────────────────────────────────────────
# check_thesis_overdue tests (Requirement 9.3)
# ──────────────────────────────────────────────────────────────────────────────

from monitor import check_thesis_overdue


class TestCheckThesisOverdue:
    """Tests for check_thesis_overdue() — persistent overdue alerts every cycle."""

    def test_overdue_position_emits_alert(self):
        """Active position with thesis_status='review_overdue' appears in alerts."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "active",
                    "thesis_status": "review_overdue",
                    "overdue_since": "2025-06-01",
                }
            ]
        }
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert alerts[0].category == "holding"
        assert "XOM" in alerts[0].message
        assert "flagged since 2025-06-01" in alerts[0].message

    def test_reviewed_position_no_alert(self):
        """Active position with thesis_status='reviewed' does NOT appear in alerts."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "active",
                    "thesis_status": "reviewed",
                    "overdue_since": "2025-06-01",
                }
            ]
        }
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 0

    def test_closed_overdue_position_no_alert(self):
        """Closed position with thesis_status='review_overdue' does NOT appear."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "closed",
                    "thesis_status": "review_overdue",
                    "overdue_since": "2025-06-01",
                }
            ]
        }
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 0

    def test_multiple_overdue_positions(self):
        """Multiple overdue positions all appear in alerts."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "active",
                    "thesis_status": "review_overdue",
                    "overdue_since": "2025-06-01",
                },
                {
                    "ticker": "AAPL",
                    "status": "active",
                    "thesis_status": "review_overdue",
                    "overdue_since": "2025-06-05",
                },
                {
                    "ticker": "GOOG",
                    "status": "active",
                    "thesis_status": "active",
                },
            ]
        }
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 2
        tickers = [a.ticker for a in alerts]
        assert "XOM" in tickers
        assert "AAPL" in tickers

    def test_overdue_alert_includes_days_count(self):
        """Alert message includes the number of days overdue."""
        book = {
            "positions": [
                {
                    "ticker": "XOM",
                    "status": "active",
                    "thesis_status": "review_overdue",
                    "overdue_since": (date.today() - timedelta(days=10)).isoformat(),
                }
            ]
        }
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 1
        assert "10 days overdue" in alerts[0].message

    def test_no_positions_returns_empty(self):
        """Empty book returns no alerts."""
        book = {"positions": []}
        alerts = check_thesis_overdue(book)
        assert len(alerts) == 0
