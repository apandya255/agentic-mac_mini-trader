# Feature: live-data-automated-recommendations, Property 1: Market Hours Classification
# Feature: live-data-automated-recommendations, Property 4: Trading Day Holiday Check
"""
Property-based tests for src/data_platform/market_calendar.py

Validates: Requirements 16.1, 16.2, 16.6, 1.1, 1.5
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytz
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.data_platform.market_calendar import (
    ET,
    MARKET_CLOSE,
    MARKET_OPEN,
    US_MARKET_HOLIDAYS,
    _HOLIDAY_DATES,
    is_market_open,
    is_trading_day,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate a datetime during regular market hours on a trading day
# Steps: pick a non-holiday weekday, then pick a time within 09:30-15:59 ET
_TRADING_DATES_2025_2026: list[date] = [
    date(2025, 1, 1) + timedelta(days=i)
    for i in range((date(2026, 12, 31) - date(2025, 1, 1)).days + 1)
    if (date(2025, 1, 1) + timedelta(days=i)).weekday() < 5
    and (date(2025, 1, 1) + timedelta(days=i)) not in _HOLIDAY_DATES
]

_HOLIDAY_DATES_LIST: list[date] = [d for d in _HOLIDAY_DATES if date(2025, 1, 1) <= d <= date(2026, 12, 31)]

_WEEKEND_DATES_2025_2026: list[date] = [
    date(2025, 1, 1) + timedelta(days=i)
    for i in range((date(2026, 12, 31) - date(2025, 1, 1)).days + 1)
    if (date(2025, 1, 1) + timedelta(days=i)).weekday() >= 5
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


# Strategy for dates in 2025-2027 range (for Property 4)
_ALL_DATES_2025_2027 = st.dates(
    min_value=date(2025, 1, 1),
    max_value=date(2027, 12, 31),
)


# ---------------------------------------------------------------------------
# Property 1: Market Hours Classification
# ---------------------------------------------------------------------------
# For any datetime during US equity market regular session (Monday-Friday,
# 09:30-16:00 ET, non-holiday), is_market_open() SHALL return True;
# for any datetime outside those hours (weekends, before 09:30, after 16:00,
# or US market holidays), is_market_open() SHALL return False.
#
# Validates: Requirements 1.1, 1.5
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_market_hours_time(),
)
def test_property_1_market_open_during_regular_session(d: date, t: time):
    """
    **Validates: Requirements 16.1, 16.2**

    Property 1: For any datetime during regular session (weekday, non-holiday,
    09:30 <= time < 16:00 ET), is_market_open() returns True.
    """
    dt_et = ET.localize(datetime.combine(d, t))
    assert is_market_open(dt_et) is True


@settings(max_examples=200)
@given(
    d=st.sampled_from(_TRADING_DATES_2025_2026),
    t=_outside_market_hours_time(),
)
def test_property_1_market_closed_outside_hours_on_trading_day(d: date, t: time):
    """
    **Validates: Requirements 16.1, 16.2**

    Property 1: For any trading day datetime outside 09:30-16:00 ET,
    is_market_open() returns False.
    """
    dt_et = ET.localize(datetime.combine(d, t))
    assert is_market_open(dt_et) is False


@settings(max_examples=200)
@given(
    d=st.sampled_from(_WEEKEND_DATES_2025_2026),
    t=st.times(),
)
def test_property_1_market_closed_on_weekends(d: date, t: time):
    """
    **Validates: Requirements 16.1, 1.5**

    Property 1 (subset): For any weekend datetime, is_market_open() returns False.
    """
    dt_et = ET.localize(datetime.combine(d, t))
    assert is_market_open(dt_et) is False


@settings(max_examples=200)
@given(
    d=st.sampled_from(_HOLIDAY_DATES_LIST),
    t=st.times(),
)
def test_property_1_market_closed_on_holidays(d: date, t: time):
    """
    **Validates: Requirements 16.6, 1.5**

    Property 1 (subset): For any US market holiday, is_market_open() returns
    False regardless of time.
    """
    dt_et = ET.localize(datetime.combine(d, t))
    assert is_market_open(dt_et) is False


# ---------------------------------------------------------------------------
# Property 4: Trading Day Holiday Check
# ---------------------------------------------------------------------------
# For any date that is a US market holiday (from the static list) or a weekend,
# is_trading_day() SHALL return False. For any weekday that is not in the
# holiday list, is_trading_day() SHALL return True.
#
# Validates: Requirements 16.6, 1.1, 1.5
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(d=_ALL_DATES_2025_2027)
def test_property_4_non_trading_days(d: date):
    """
    **Validates: Requirements 16.6, 1.5**

    Property 4: For any holiday or weekend, is_trading_day() returns False.
    """
    is_weekend = d.weekday() >= 5
    is_holiday = d in _HOLIDAY_DATES

    assume(is_weekend or is_holiday)

    assert is_trading_day(d) is False


@settings(max_examples=200)
@given(d=_ALL_DATES_2025_2027)
def test_property_4_valid_trading_days(d: date):
    """
    **Validates: Requirements 16.6, 1.1**

    Property 4: For any weekday that is NOT a US market holiday,
    is_trading_day() returns True.
    """
    is_weekday = d.weekday() < 5
    is_not_holiday = d not in _HOLIDAY_DATES

    assume(is_weekday and is_not_holiday)

    assert is_trading_day(d) is True
