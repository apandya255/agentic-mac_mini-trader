# Feature: operational-reliability, Property 3: Alpha Vantage Rate Limiting
"""
Property-based tests for Alpha Vantage rate limiting.

Property 3: For any sequence of N Alpha Vantage fetch attempts occurring within
a 60-second window, at most 5 SHALL actually execute without blocking; the
remainder SHALL be delayed until the next minute boundary.

**Validates: Requirements 2.4**
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.data_platform.prices import _AVRateLimiter


# ---------------------------------------------------------------------------
# Property 3a: At most max_calls execute without blocking within the period
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(n=st.integers(min_value=1, max_value=20))
def test_property_3_at_most_5_calls_without_blocking(n: int):
    """
    **Validates: Requirements 2.4**

    Property 3: For any sequence of N fetch attempts (N from 1 to 20) occurring
    within a 60-second window, at most 5 SHALL actually execute without blocking.
    Calls 1-5 do not sleep; calls 6+ trigger sleep.
    """
    limiter = _AVRateLimiter(max_calls=5, period=60.0)
    sleep_calls: list[float] = []
    fake_now = 1000.0  # fixed time to simulate all calls within same window

    def mock_time():
        return fake_now

    def mock_sleep(duration):
        sleep_calls.append(duration)

    with patch("time.time", side_effect=mock_time), patch(
        "time.sleep", side_effect=mock_sleep
    ):
        for _ in range(n):
            limiter.acquire()

    # For calls 1 through min(n, 5), no sleep should occur
    # For calls beyond 5, sleep IS called
    if n <= 5:
        assert len(sleep_calls) == 0, (
            f"Expected no sleep for {n} calls (<=5), but got {len(sleep_calls)} sleep calls"
        )
    else:
        assert len(sleep_calls) == n - 5, (
            f"Expected {n - 5} sleep calls for {n} attempts (only first 5 are free), "
            f"but got {len(sleep_calls)}"
        )


# ---------------------------------------------------------------------------
# Property 3b: Non-blocking call count is exactly min(N, max_calls)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(n=st.integers(min_value=1, max_value=20))
def test_property_3_non_blocking_count_is_min_n_max_calls(n: int):
    """
    **Validates: Requirements 2.4**

    Property 3: Count how many calls complete without sleeping — should be
    exactly min(N, 5).
    """
    limiter = _AVRateLimiter(max_calls=5, period=60.0)
    non_blocking_count = 0
    fake_now = 1000.0

    def mock_time():
        return fake_now

    def mock_sleep(duration):
        pass  # Don't actually sleep, just track

    with patch("time.time", side_effect=mock_time), patch(
        "time.sleep", side_effect=mock_sleep
    ):
        for i in range(n):
            sleep_tracker: list[float] = []
            with patch("time.sleep", side_effect=lambda d: sleep_tracker.append(d)):
                with patch("time.time", side_effect=lambda: fake_now):
                    # Reset limiter's internal state tracking for this call
                    pass

            # Actually test each call individually to track blocking
            pass

    # Simpler approach: track per-call blocking
    limiter = _AVRateLimiter(max_calls=5, period=60.0)
    non_blocking = 0
    fake_now = 1000.0

    def mock_time_2():
        return fake_now

    with patch("time.time", side_effect=mock_time_2):
        for _ in range(n):
            blocked = [False]

            def track_sleep(duration, _blocked=blocked):
                _blocked[0] = True

            with patch("time.sleep", side_effect=track_sleep):
                limiter.acquire()
                if not blocked[0]:
                    non_blocking += 1

    expected = min(n, 5)
    assert non_blocking == expected, (
        f"Expected {expected} non-blocking calls for N={n}, but got {non_blocking}"
    )


# ---------------------------------------------------------------------------
# Property 3c: After period expires, limiter allows max_calls new calls
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    period=st.floats(min_value=1.0, max_value=120.0, allow_nan=False, allow_infinity=False),
    max_calls=st.integers(min_value=1, max_value=10),
)
def test_property_3_period_expiry_allows_new_calls(period: float, max_calls: int):
    """
    **Validates: Requirements 2.4**

    Property 3 (converse): For any period P and max_calls M, after P seconds
    have elapsed since the first call, the limiter allows M new calls without
    blocking.
    """
    limiter = _AVRateLimiter(max_calls=max_calls, period=period)
    current_time = [1000.0]

    def mock_time():
        return current_time[0]

    def mock_sleep(duration):
        # Advance time when sleep is called (simulates waiting)
        current_time[0] += duration

    # Phase 1: Exhaust all slots at time=1000.0
    with patch("time.time", mock_time), patch("time.sleep", mock_sleep):
        for _ in range(max_calls):
            limiter.acquire()

    # Phase 2: Advance time past the period
    current_time[0] = 1000.0 + period + 0.01

    # Phase 3: All new calls should go through without blocking
    sleep_calls: list[float] = []

    def track_sleep(duration):
        sleep_calls.append(duration)

    with patch("time.time", mock_time), patch("time.sleep", track_sleep):
        for _ in range(max_calls):
            limiter.acquire()

    assert len(sleep_calls) == 0, (
        f"Expected no sleep after period ({period}s) expired, "
        f"but got {len(sleep_calls)} sleep calls. "
        f"max_calls={max_calls}"
    )
