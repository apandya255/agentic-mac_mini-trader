# Feature: operational-reliability, Property 1: Retry Backoff Timing
# Feature: operational-reliability, Property 4: Weekend Staleness Suppression
"""
Property-based tests for retry backoff timing and weekend/holiday staleness
suppression in the operational-reliability feature.

Validates: Requirements 1.1, 3.1, 3.2
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytz
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.data_platform.market_calendar import (
    ET,
    US_MARKET_HOLIDAYS,
    _HOLIDAY_DATES,
    is_equity_stale_check_suppressed,
    is_fx_stale_check_suppressed,
)
from src.data_platform.prices import PriceService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Pre-compute weekend dates for 2025-2026 range
_WEEKEND_DATES_2025_2026: list[date] = [
    date(2025, 1, 1) + timedelta(days=i)
    for i in range((date(2026, 12, 31) - date(2025, 1, 1)).days + 1)
    if (date(2025, 1, 1) + timedelta(days=i)).weekday() >= 5
]

# Pre-compute holiday dates for 2025-2026 range
_HOLIDAY_DATES_LIST: list[date] = [
    d for d in _HOLIDAY_DATES if date(2025, 1, 1) <= d <= date(2026, 12, 31)
]

# Saturday dates only (weekday() == 5)
_SATURDAY_DATES: list[date] = [
    d for d in _WEEKEND_DATES_2025_2026 if d.weekday() == 5
]

# Sunday dates only (weekday() == 6)
_SUNDAY_DATES: list[date] = [
    d for d in _WEEKEND_DATES_2025_2026 if d.weekday() == 6
]


# ---------------------------------------------------------------------------
# Property 1: Retry Backoff Timing
# ---------------------------------------------------------------------------
# For any retry count N in [0, 1, 2, 3], the cumulative delay before the Nth
# retry equals sum(2^i for i in range(1, N+1)).
# i.e., 0 retries = 0s total delay, 1 retry = 2s, 2 retries = 6s (2+4),
# 3 retries = 14s (2+4+8)
#
# Validates: Requirements 1.1
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(n_failures=st.integers(min_value=0, max_value=3))
def test_property_1_retry_backoff_cumulative_delay(n_failures: int):
    """
    **Validates: Requirements 1.1**

    Property 1: Retry Backoff Timing — For any retry count N in [0, 1, 2, 3],
    the cumulative delay (sum of all sleep calls) matches
    sum(2**(i+1) for i in range(N)).

    When n_failures < max_retries+1, yfinance fails N times then succeeds.
    When n_failures == max_retries (3), all retries are exhausted.
    """
    import tempfile
    from pathlib import Path

    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_prices.db"
        svc = PriceService(db_path=db_path)

        # Create a mock DataFrame for successful responses
        mock_df = pd.DataFrame(
            {"Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000]},
            index=pd.to_datetime(["2025-01-02"]),
        )

        # Build side effects: n_failures exceptions followed by success (if not exhausted)
        max_retries = 3
        total_attempts = max_retries + 1  # initial + retries

        if n_failures < total_attempts:
            side_effects = [Exception(f"transient failure {i}") for i in range(n_failures)]
            side_effects.append(mock_df)
        else:
            # All attempts fail (n_failures == 3 means 3 retries fail after initial)
            side_effects = [Exception(f"persistent failure {i}") for i in range(total_attempts)]

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("yfinance.download", side_effect=side_effects):
            with patch("time.sleep", side_effect=mock_sleep):
                svc._fetch_with_retry("TEST", date(2025, 1, 1), max_retries=max_retries)

        # Verify: number of sleep calls equals the number of retries that occurred
        expected_sleep_count = min(n_failures, max_retries)
        assert len(sleep_calls) == expected_sleep_count, (
            f"Expected {expected_sleep_count} sleep calls for {n_failures} failures, "
            f"got {len(sleep_calls)}"
        )

        # Verify: cumulative delay matches sum(2^(i+1) for i in range(sleep_count))
        expected_cumulative = sum(2 ** (i + 1) for i in range(expected_sleep_count))
        actual_cumulative = sum(sleep_calls)
        assert actual_cumulative == expected_cumulative, (
            f"Expected cumulative delay {expected_cumulative}s for {expected_sleep_count} retries, "
            f"got {actual_cumulative}s (individual sleeps: {sleep_calls})"
        )

        # Verify: individual delays follow 2^(i+1) pattern
        for i, delay in enumerate(sleep_calls):
            expected_delay = 2 ** (i + 1)
            assert delay == expected_delay, (
                f"Retry {i}: expected {expected_delay}s delay, got {delay}s"
            )


# ---------------------------------------------------------------------------
# Property 4: Weekend Staleness Suppression
# ---------------------------------------------------------------------------
# For any datetime that falls on a Saturday, Sunday, or US market holiday,
# equity tickers SHALL NOT be flagged as STALE (is_equity_stale_check_suppressed
# returns True). For FX, suppression applies on Saturday and Sunday before
# 17:00 ET.
#
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    d=st.sampled_from(_WEEKEND_DATES_2025_2026),
    t=st.times(),
)
def test_property_4_equity_staleness_suppressed_on_weekends(d: date, t: time):
    """
    **Validates: Requirements 3.1**

    Property 4: Weekend Staleness Suppression — For any datetime on Saturday
    or Sunday, is_equity_stale_check_suppressed() returns True (no stale flag
    raised for equity tickers).
    """
    dt_et = ET.localize(datetime.combine(d, t))
    result = is_equity_stale_check_suppressed(dt_et)
    assert result is True, (
        f"Expected equity staleness suppressed on weekend {d} ({d.strftime('%A')}) "
        f"at {t}, but got False"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_HOLIDAY_DATES_LIST),
    t=st.times(),
)
def test_property_4_equity_staleness_suppressed_on_holidays(d: date, t: time):
    """
    **Validates: Requirements 3.1**

    Property 4: Weekend Staleness Suppression — For any US market holiday
    datetime, is_equity_stale_check_suppressed() returns True (no stale flag
    raised for equity tickers).
    """
    dt_et = ET.localize(datetime.combine(d, t))
    result = is_equity_stale_check_suppressed(dt_et)
    assert result is True, (
        f"Expected equity staleness suppressed on holiday {d} at {t}, "
        f"but got False"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_SATURDAY_DATES),
    t=st.times(),
)
def test_property_4_fx_staleness_suppressed_on_saturdays(d: date, t: time):
    """
    **Validates: Requirements 3.2**

    Property 4: Weekend Staleness Suppression — For any Saturday datetime,
    is_fx_stale_check_suppressed() returns True (FX session is fully inactive
    on Saturdays).
    """
    dt_et = ET.localize(datetime.combine(d, t))
    result = is_fx_stale_check_suppressed(dt_et)
    assert result is True, (
        f"Expected FX staleness suppressed on Saturday {d} at {t}, "
        f"but got False"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_SUNDAY_DATES),
    t=st.times(min_value=time(0, 0, 0), max_value=time(16, 59, 59)),
)
def test_property_4_fx_staleness_suppressed_on_sunday_before_session_open(d: date, t: time):
    """
    **Validates: Requirements 3.2**

    Property 4: Weekend Staleness Suppression — For any Sunday datetime
    before 17:00 ET, is_fx_stale_check_suppressed() returns True (FX session
    has not yet opened).
    """
    dt_et = ET.localize(datetime.combine(d, t))
    result = is_fx_stale_check_suppressed(dt_et)
    assert result is True, (
        f"Expected FX staleness suppressed on Sunday {d} before 17:00 ET "
        f"(time={t}), but got False"
    )


@settings(max_examples=200)
@given(
    d=st.sampled_from(_SUNDAY_DATES),
    t=st.times(min_value=time(17, 0, 0), max_value=time(23, 59, 59)),
)
def test_property_4_fx_staleness_not_suppressed_on_sunday_after_session_open(d: date, t: time):
    """
    **Validates: Requirements 3.2**

    Property 4: Confirms FX session is ACTIVE on Sunday at/after 17:00 ET,
    so staleness checks are NOT suppressed (is_fx_stale_check_suppressed
    returns False — meaning FX quotes should be monitored for freshness).
    """
    dt_et = ET.localize(datetime.combine(d, t))
    result = is_fx_stale_check_suppressed(dt_et)
    assert result is False, (
        f"Expected FX staleness NOT suppressed on Sunday {d} at/after 17:00 ET "
        f"(time={t}), but got True — FX session should be active"
    )
