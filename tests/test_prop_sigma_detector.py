"""
Property-based tests for src/trading/sigma_detector.py

Property 10: Sigma event detection is symmetric and threshold-based

For any position with at least 20 days of price history, the sigma event detector
SHALL trigger if and only if |daily_change_pct| > 2 × trailing_20day_stddev.
The detection is symmetric — positive and negative moves of the same magnitude
both trigger (or both don't).

**Validates: Requirements 6.1, 6.2, 6.3**
"""

from __future__ import annotations

import math
import os
import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.sigma_detector import compute_trailing_stddev, detect_sigma_event

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate trailing 20-day changes with non-zero variance
# We use floats in a reasonable range for daily percentage changes (e.g. -20% to +20%)
daily_change_st = st.floats(min_value=-0.20, max_value=0.20, allow_nan=False, allow_infinity=False)

# A list of at least 2 trailing changes (to ensure non-zero stddev is possible)
trailing_changes_st = st.lists(
    daily_change_st,
    min_size=2,
    max_size=40,
)

# Strategy for the current day's change — broader range to test both trigger and no-trigger
current_change_st = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Strategy for threshold_sigmas (always use default 2.0 per the spec)
threshold_st = st.just(2.0)


# ---------------------------------------------------------------------------
# Property 10: Sigma event detection is symmetric and threshold-based
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(
    daily_change_pct=current_change_st,
    trailing_changes=trailing_changes_st,
)
def test_property_10_symmetry(daily_change_pct: float, trailing_changes: list[float]):
    """
    **Validates: Requirements 6.1, 6.2, 6.3**

    Property 10 (Symmetry): For any daily change, the sigma event detector
    triggers for +X iff it also triggers for -X (same magnitude, opposite sign).
    Detection depends only on |daily_change_pct|, not on direction.
    """
    stddev = compute_trailing_stddev(trailing_changes)
    assume(stddev > 0.0)  # Need non-zero stddev for meaningful test

    result_positive = detect_sigma_event(abs(daily_change_pct), trailing_changes)
    result_negative = detect_sigma_event(-abs(daily_change_pct), trailing_changes)

    # Both should trigger or both should not trigger
    triggered_positive = result_positive is not None
    triggered_negative = result_negative is not None

    assert triggered_positive == triggered_negative, (
        f"Asymmetric detection: +{abs(daily_change_pct)} triggered={triggered_positive}, "
        f"-{abs(daily_change_pct)} triggered={triggered_negative}, stddev={stddev}"
    )


@settings(max_examples=500)
@given(
    daily_change_pct=current_change_st,
    trailing_changes=trailing_changes_st,
)
def test_property_10_threshold_iff(daily_change_pct: float, trailing_changes: list[float]):
    """
    **Validates: Requirements 6.1, 6.2, 6.3**

    Property 10 (Threshold IFF): The sigma event triggers if and only if
    |daily_change_pct| > 2 × trailing_20day_stddev (when stddev > 0).
    """
    stddev = compute_trailing_stddev(trailing_changes)
    assume(stddev > 0.0)

    threshold = 2.0 * stddev
    result = detect_sigma_event(daily_change_pct, trailing_changes, threshold_sigmas=2.0)

    should_trigger = abs(daily_change_pct) > threshold

    if should_trigger:
        assert result is not None, (
            f"|{daily_change_pct}| = {abs(daily_change_pct)} > threshold {threshold} "
            f"but detect_sigma_event returned None"
        )
        assert result["triggered"] is True
        assert result["magnitude"] == daily_change_pct
        assert math.isclose(result["threshold_2sigma"], threshold, rel_tol=1e-9)
        assert math.isclose(result["trailing_stddev"], stddev, rel_tol=1e-9)
    else:
        assert result is None, (
            f"|{daily_change_pct}| = {abs(daily_change_pct)} <= threshold {threshold} "
            f"but detect_sigma_event returned {result}"
        )


@settings(max_examples=300)
@given(
    length=st.integers(min_value=0, max_value=1),
    daily_change_pct=current_change_st,
)
def test_property_10_insufficient_data_never_triggers(
    length: int, daily_change_pct: float
):
    """
    **Validates: Requirements 6.1, 6.2, 6.3**

    Property 10 (Insufficient data guard): When fewer than 2 data points are
    available, compute_trailing_stddev returns 0.0 and the detector never
    triggers regardless of the daily change magnitude.
    """
    trailing_changes = [0.01] * length  # 0 or 1 elements

    stddev = compute_trailing_stddev(trailing_changes)
    assert stddev == 0.0

    result = detect_sigma_event(daily_change_pct, trailing_changes, threshold_sigmas=2.0)
    assert result is None, (
        f"Sigma event triggered with insufficient data (length={length}) "
        f"for change={daily_change_pct}"
    )


@settings(max_examples=300)
@given(
    daily_change_pct=current_change_st,
    trailing_changes=st.lists(daily_change_st, min_size=20, max_size=40),
)
def test_property_10_stddev_uses_last_20(daily_change_pct: float, trailing_changes: list[float]):
    """
    **Validates: Requirements 6.3**

    Property 10 (20-day window): The trailing standard deviation is computed
    from the last 20 values of the input. The test verifies that compute_trailing_stddev
    produces the correct sample stddev over that window.
    """
    # Manually compute expected stddev from last 20 values
    data = trailing_changes[-20:]
    n = len(data)
    assume(n >= 2)

    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / (n - 1)
    expected_stddev = math.sqrt(variance)

    actual_stddev = compute_trailing_stddev(trailing_changes)

    assert math.isclose(actual_stddev, expected_stddev, rel_tol=1e-9), (
        f"Stddev mismatch: expected {expected_stddev}, got {actual_stddev}"
    )
