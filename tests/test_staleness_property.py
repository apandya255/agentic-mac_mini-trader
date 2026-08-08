# Feature: live-data-automated-recommendations, Property 5: Staleness Detection
"""
Property-based tests for staleness detection logic.

Property 5: For any `last_marked` timestamp and current time during market hours,
the `_stale` flag SHALL be True if and only if the elapsed time exceeds
`POLL_INTERVAL_MINUTES + 0.5` minutes. Outside market hours, `_stale` SHALL
always be False.

**Validates: Requirements 14.5, 18.4**
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytz
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.data_platform.market_calendar import (
    ET,
    MARKET_CLOSE,
    MARKET_OPEN,
    _HOLIDAY_DATES,
    is_market_open,
)

# ---------------------------------------------------------------------------
# Staleness Detection Logic Under Test
# ---------------------------------------------------------------------------
# This mirrors the logic implemented in serve.py's /api/book endpoint and the
# dashboard staleness indicator. We extract it as a pure function for testing.


def compute_stale_flag(
    last_marked: str | None,
    current_time: datetime,
    poll_interval_minutes: int,
) -> bool:
    """
    Compute the _stale flag for the book API response.

    Args:
        last_marked: ISO-format timestamp of the last mark-to-market, or None.
        current_time: The current datetime (timezone-aware in ET).
        poll_interval_minutes: The configured POLL_INTERVAL_MINUTES value.

    Returns:
        True if data is stale (elapsed > interval + 0.5 during market hours),
        False otherwise.
    """
    if last_marked and is_market_open(current_time):
        last_marked_dt = datetime.fromisoformat(last_marked)
        # Ensure both datetimes are comparable (timezone-aware)
        if last_marked_dt.tzinfo is None:
            last_marked_dt = ET.localize(last_marked_dt)
        if current_time.tzinfo is None:
            current_time = ET.localize(current_time)
        age_minutes = (current_time - last_marked_dt).total_seconds() / 60
        return age_minutes > (poll_interval_minutes + 0.5)
    else:
        return False


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Datetimes in the 2025-2026 range
_datetimes_2025_2026 = st.datetimes(
    min_value=datetime(2025, 1, 1),
    max_value=datetime(2026, 12, 31),
)

# POLL_INTERVAL_MINUTES: 1 to 60
_poll_intervals = st.integers(min_value=1, max_value=60)

# Pre-compute trading dates for market-hours strategies
_TRADING_DATES_2025_2026: list[date] = [
    date(2025, 1, 1) + timedelta(days=i)
    for i in range((date(2026, 12, 31) - date(2025, 1, 1)).days + 1)
    if (date(2025, 1, 1) + timedelta(days=i)).weekday() < 5
    and (date(2025, 1, 1) + timedelta(days=i)) not in _HOLIDAY_DATES
]

_WEEKEND_DATES_2025_2026: list[date] = [
    date(2025, 1, 1) + timedelta(days=i)
    for i in range((date(2026, 12, 31) - date(2025, 1, 1)).days + 1)
    if (date(2025, 1, 1) + timedelta(days=i)).weekday() >= 5
]

_HOLIDAY_DATES_LIST: list[date] = [
    d for d in _HOLIDAY_DATES if date(2025, 1, 1) <= d <= date(2026, 12, 31)
]


def _market_hours_time():
    """Strategy that generates times between 09:30:00 and 15:59:59."""
    return st.times(
        min_value=time(9, 30, 0),
        max_value=time(15, 59, 59),
    )


def _outside_market_hours_time():
    """Strategy that generates times outside 09:30-16:00."""
    return st.one_of(
        st.times(min_value=time(0, 0, 0), max_value=time(9, 29, 59)),
        st.times(min_value=time(16, 0, 0), max_value=time(23, 59, 59)),
    )


# ---------------------------------------------------------------------------
# Property 5a: During market hours, stale iff elapsed > interval + 0.5
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_market_hours_time(),
    poll_interval=_poll_intervals,
    elapsed_minutes=st.floats(min_value=0.0, max_value=120.0, allow_nan=False, allow_infinity=False),
)
def test_property_5_stale_true_when_elapsed_exceeds_threshold(
    d: date, t: time, poll_interval: int, elapsed_minutes: float
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: During market hours, if elapsed time > POLL_INTERVAL_MINUTES + 0.5,
    then _stale SHALL be True.
    """
    threshold = poll_interval + 0.5
    assume(elapsed_minutes > threshold)

    current_time = ET.localize(datetime.combine(d, t))
    last_marked_dt = current_time - timedelta(minutes=elapsed_minutes)
    last_marked_str = last_marked_dt.isoformat()

    result = compute_stale_flag(last_marked_str, current_time, poll_interval)
    assert result is True, (
        f"Expected stale=True when elapsed={elapsed_minutes:.2f}m > "
        f"threshold={threshold:.1f}m during market hours"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_market_hours_time(),
    poll_interval=_poll_intervals,
    elapsed_minutes=st.floats(min_value=0.0, max_value=60.5, allow_nan=False, allow_infinity=False),
)
def test_property_5_stale_false_when_elapsed_within_threshold(
    d: date, t: time, poll_interval: int, elapsed_minutes: float
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: During market hours, if elapsed time <= POLL_INTERVAL_MINUTES + 0.5,
    then _stale SHALL be False.
    """
    threshold = poll_interval + 0.5
    assume(elapsed_minutes <= threshold)

    current_time = ET.localize(datetime.combine(d, t))
    last_marked_dt = current_time - timedelta(minutes=elapsed_minutes)
    last_marked_str = last_marked_dt.isoformat()

    result = compute_stale_flag(last_marked_str, current_time, poll_interval)
    assert result is False, (
        f"Expected stale=False when elapsed={elapsed_minutes:.2f}m <= "
        f"threshold={threshold:.1f}m during market hours"
    )


# ---------------------------------------------------------------------------
# Property 5b: Outside market hours, stale is always False
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    d=st.sampled_from(_WEEKEND_DATES_2025_2026),
    t=st.times(),
    poll_interval=_poll_intervals,
    elapsed_minutes=st.floats(min_value=0.0, max_value=1440.0, allow_nan=False, allow_infinity=False),
)
def test_property_5_stale_false_on_weekends(
    d: date, t: time, poll_interval: int, elapsed_minutes: float
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: Outside market hours (weekends), _stale SHALL always be False
    regardless of elapsed time.
    """
    current_time = ET.localize(datetime.combine(d, t))
    last_marked_dt = current_time - timedelta(minutes=elapsed_minutes)
    last_marked_str = last_marked_dt.isoformat()

    result = compute_stale_flag(last_marked_str, current_time, poll_interval)
    assert result is False, (
        f"Expected stale=False on weekend ({d}, {t}) regardless of "
        f"elapsed={elapsed_minutes:.2f}m"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_outside_market_hours_time(),
    poll_interval=_poll_intervals,
    elapsed_minutes=st.floats(min_value=0.0, max_value=1440.0, allow_nan=False, allow_infinity=False),
)
def test_property_5_stale_false_outside_market_hours_on_trading_day(
    d: date, t: time, poll_interval: int, elapsed_minutes: float
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: Outside market hours (before 09:30 or after 16:00 on trading day),
    _stale SHALL always be False regardless of elapsed time.
    """
    current_time = ET.localize(datetime.combine(d, t))
    last_marked_dt = current_time - timedelta(minutes=elapsed_minutes)
    last_marked_str = last_marked_dt.isoformat()

    result = compute_stale_flag(last_marked_str, current_time, poll_interval)
    assert result is False, (
        f"Expected stale=False outside market hours ({d} {t}) regardless of "
        f"elapsed={elapsed_minutes:.2f}m"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_HOLIDAY_DATES_LIST),
    t=st.times(),
    poll_interval=_poll_intervals,
    elapsed_minutes=st.floats(min_value=0.0, max_value=1440.0, allow_nan=False, allow_infinity=False),
)
def test_property_5_stale_false_on_holidays(
    d: date, t: time, poll_interval: int, elapsed_minutes: float
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: On US market holidays, _stale SHALL always be False
    regardless of elapsed time (market is not open).
    """
    current_time = ET.localize(datetime.combine(d, t))
    last_marked_dt = current_time - timedelta(minutes=elapsed_minutes)
    last_marked_str = last_marked_dt.isoformat()

    result = compute_stale_flag(last_marked_str, current_time, poll_interval)
    assert result is False, (
        f"Expected stale=False on holiday ({d}) regardless of "
        f"elapsed={elapsed_minutes:.2f}m"
    )


# ---------------------------------------------------------------------------
# Property 5c: No last_marked → stale is always False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_market_hours_time(),
    poll_interval=_poll_intervals,
)
def test_property_5_stale_false_when_no_last_marked(
    d: date, t: time, poll_interval: int
):
    """
    **Validates: Requirements 14.5, 18.4**

    Property 5: When last_marked is None (no prior poll), _stale SHALL be False
    even during market hours.
    """
    current_time = ET.localize(datetime.combine(d, t))

    result = compute_stale_flag(None, current_time, poll_interval)
    assert result is False, "Expected stale=False when last_marked is None"
