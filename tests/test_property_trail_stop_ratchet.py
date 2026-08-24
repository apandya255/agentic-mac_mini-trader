# Feature: operational-reliability, Property 7: Trail Stop Monotonic Ratchet
"""
Property-based tests for trail stop monotonic ratchet behavior.

For all monotonically increasing peak price sequences, trail stops never
decrease (long positions) or increase (short positions).

Validates: Requirements 7.2, 7.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from monitor import compute_trail_stop_level, ratchet_trail_stop


# ---------------------------------------------------------------------------
# Property 7: Trail Stop Monotonic Ratchet
# ---------------------------------------------------------------------------
# For any sequence of peak prices [p1, p2, ..., pN] where each pi >= p(i-1),
# the corresponding trail stop levels (after ratchet) SHALL be monotonically
# non-decreasing for long positions.
#
# For any sequence of peak prices [p1, p2, ..., pN] where each pi <= p(i-1),
# the corresponding trail stop levels (after ratchet) SHALL be monotonically
# non-increasing for short positions.
#
# Validates: Requirements 7.2, 7.3
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    prices=st.lists(
        st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=20,
    )
)
def test_property_7_trail_stop_monotonic_ratchet_long(prices: list[float]):
    """
    **Validates: Requirements 7.2, 7.3**

    Property 7: Trail Stop Monotonic Ratchet (Long) — For all monotonically
    increasing peak price sequences, computing trail stops and applying ratchet
    produces monotonically non-decreasing trail stop levels for long positions.
    """
    # Sort prices to create a monotonically increasing peak sequence
    sorted_peaks = sorted(prices)
    entry_price = sorted_peaks[0]

    trail_levels: list[float] = []
    existing_level: float | None = None

    for peak in sorted_peaks:
        new_level = compute_trail_stop_level(entry_price, peak, "long")
        ratcheted = ratchet_trail_stop(new_level, existing_level, "long")
        trail_levels.append(ratcheted)
        existing_level = ratcheted

    # Assert monotonically non-decreasing: each level >= previous
    for i in range(1, len(trail_levels)):
        assert trail_levels[i] >= trail_levels[i - 1], (
            f"Trail stop decreased for long position at step {i}: "
            f"trail_levels[{i-1}]={trail_levels[i-1]}, "
            f"trail_levels[{i}]={trail_levels[i]}, "
            f"peaks={sorted_peaks[:i+1]}"
        )


@settings(max_examples=200)
@given(
    prices=st.lists(
        st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=20,
    )
)
def test_property_7_trail_stop_monotonic_ratchet_short(prices: list[float]):
    """
    **Validates: Requirements 7.2, 7.3**

    Property 7: Trail Stop Monotonic Ratchet (Short) — For all monotonically
    decreasing peak price sequences, computing trail stops and applying ratchet
    produces monotonically non-increasing trail stop levels for short positions.
    """
    # Sort prices in descending order to create a monotonically decreasing peak sequence
    sorted_peaks = sorted(prices, reverse=True)
    entry_price = sorted_peaks[0]

    trail_levels: list[float] = []
    existing_level: float | None = None

    for peak in sorted_peaks:
        new_level = compute_trail_stop_level(entry_price, peak, "short")
        ratcheted = ratchet_trail_stop(new_level, existing_level, "short")
        trail_levels.append(ratcheted)
        existing_level = ratcheted

    # Assert monotonically non-increasing: each level <= previous
    for i in range(1, len(trail_levels)):
        assert trail_levels[i] <= trail_levels[i - 1], (
            f"Trail stop increased for short position at step {i}: "
            f"trail_levels[{i-1}]={trail_levels[i-1]}, "
            f"trail_levels[{i}]={trail_levels[i]}, "
            f"peaks={sorted_peaks[:i+1]}"
        )
