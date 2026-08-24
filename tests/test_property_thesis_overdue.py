# Feature: operational-reliability, Property 10: Thesis Review Overdue Detection
"""
Property-based tests for thesis review overdue detection.

For any active position whose current date exceeds its review_date and whose
thesis_status is not "reviewed", check_thesis_break SHALL return "flag_overdue".

Validates: Requirements 9.1
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from monitor import check_thesis_break


# ---------------------------------------------------------------------------
# Property 10: Thesis Review Overdue Detection
# ---------------------------------------------------------------------------
# For any active position whose current date exceeds its review_date and whose
# thesis_status is not "reviewed", check_thesis_break SHALL return "flag_overdue".
#
# Converse: If thesis_status == "reviewed", result should NOT be "flag_overdue".
#
# Validates: Requirements 9.1
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    review_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 31)),
    days_past=st.integers(min_value=1, max_value=365),
    thesis_status=st.sampled_from(["active", "needs_review", ""]),
)
def test_property_10_thesis_review_overdue_detected(
    review_date: date,
    days_past: int,
    thesis_status: str,
):
    """
    **Validates: Requirements 9.1**

    Property 10: Thesis Review Overdue Detection — For any active position whose
    current date exceeds its review_date and whose thesis_status is not "reviewed",
    check_thesis_break SHALL return "flag_overdue".
    """
    today = review_date + timedelta(days=days_past)

    position = {
        "status": "active",
        "ticker": "TEST",
        "entry_date": (review_date - timedelta(days=30)).isoformat(),
        "review_date": review_date.isoformat(),
        "thesis_status": thesis_status,
        "expected_holding_period": "365 days",  # long enough to not trigger holding period logic
    }

    result = check_thesis_break(position, today)
    assert result == "flag_overdue", (
        f"Expected 'flag_overdue' but got {result!r} for position with "
        f"review_date={review_date}, today={today} (days_past={days_past}), "
        f"thesis_status={thesis_status!r}"
    )


@settings(max_examples=200)
@given(
    review_date=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 31)),
    days_past=st.integers(min_value=1, max_value=365),
)
def test_property_10_thesis_reviewed_not_flagged(
    review_date: date,
    days_past: int,
):
    """
    **Validates: Requirements 9.1**

    Property 10 (Converse): If thesis_status == "reviewed", the review_date path
    should NOT trigger "flag_overdue", even if review_date has passed.

    We set entry_date close to today and expected_holding_period very long to
    isolate the review_date logic from the holding-period trigger path.
    """
    today = review_date + timedelta(days=days_past)

    # Set entry_date = today - 1 day and holding period = 9999 days to ensure
    # only the review_date path is exercised (holding period never exceeded).
    position = {
        "status": "active",
        "ticker": "TEST",
        "entry_date": (today - timedelta(days=1)).isoformat(),
        "review_date": review_date.isoformat(),
        "thesis_status": "reviewed",
        "expected_holding_period": "9999 days",
    }

    result = check_thesis_break(position, today)
    assert result != "flag_overdue", (
        f"Expected result != 'flag_overdue' for reviewed position, but got {result!r} "
        f"with review_date={review_date}, today={today} (days_past={days_past})"
    )
