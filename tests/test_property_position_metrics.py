# Feature: dashboard-autonomous-revamp, Property 3: Trail stop proximity percentage is consistent with price data
# Feature: dashboard-autonomous-revamp, Property 4: Factor beta classification respects threshold ordering
# Feature: dashboard-autonomous-revamp, Property 5: Capital freed by trims aggregation is non-negative
"""
Property-based tests for dashboard computation functions (position metrics).

Property 3: Trail stop proximity percentage is consistent with price data
For any position with a trail_stop_level and current_price, the computed trail stop
proximity percentage SHALL equal (current_price - trail_stop_level) / current_price
for long positions and (trail_stop_level - current_price) / current_price for short
positions.

Property 4: Factor beta classification respects threshold ordering
For any numeric beta value, classifyFactorBeta(beta) SHALL return "green" when
|beta| < 0.4, "amber" when 0.4 <= |beta| < 0.6, and "red" when |beta| >= 0.6.
The classification SHALL be monotonically non-decreasing in severity as |beta|
increases.

Property 5: Capital freed by trims aggregation is non-negative
For any set of positions where some have trim_status of "half_trimmed",
computeCapitalFreedByTrims(positions, nav) SHALL return a non-negative value.

**Validates: Requirements 1.2, 3.4, 2.3**
"""

from __future__ import annotations

import math
import os
import sys

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Python equivalents of the client-side JS computation functions
# ---------------------------------------------------------------------------


def compute_trail_stop_proximity(position: dict | None) -> float | None:
    """
    Python equivalent of computeTrailStopProximity(position).

    Returns the percentage distance from current price to trail stop level.
    For long: (current_price - trail_stop_level) / current_price
    For short: (trail_stop_level - current_price) / current_price
    Returns None if inputs are missing/invalid.
    """
    if not position:
        return None
    trail_stop = position.get("trail_stop_level")
    current_price = position.get("current_price")
    if trail_stop is None or not current_price:
        return None
    direction = (position.get("direction") or "long").lower()
    if direction == "long":
        return (current_price - trail_stop) / current_price
    else:
        return (trail_stop - current_price) / current_price


def classify_factor_beta(beta: float | None) -> str:
    """
    Python equivalent of classifyFactorBeta(beta).

    Returns "green" when |beta| < 0.4, "amber" when 0.4 <= |beta| < 0.6,
    "red" when |beta| >= 0.6. Returns "green" for None.
    """
    if beta is None:
        return "green"
    abs_beta = abs(beta)
    if abs_beta >= 0.6:
        return "red"
    if abs_beta >= 0.4:
        return "amber"
    return "green"


def compute_capital_freed_by_trims(positions: list[dict] | None, nav: float | None) -> float:
    """
    Python equivalent of computeCapitalFreedByTrims(positions, nav).

    Sums freed capital from half_trimmed positions:
    sum of |size_pct_nav| * nav * 0.5 for positions with trim_status == 'half_trimmed'.
    Returns 0 if nav is invalid or no positions.
    """
    if not nav or nav <= 0:
        return 0.0
    if not positions:
        return 0.0
    total = 0.0
    for p in positions:
        if p.get("trim_status") == "half_trimmed":
            total += abs(p.get("size_pct_nav") or 0) * nav * 0.5
    return total


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Prices must be positive and finite
positive_price_st = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)

# Direction for positions
direction_st = st.sampled_from(["long", "short"])

# Beta values — reasonable range for factor betas
beta_st = st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False)

# NAV — positive values
nav_st = st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False)

# size_pct_nav — percentage of NAV allocated to a position
size_pct_nav_st = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Trim status options
trim_status_st = st.sampled_from(["untrimmed", "half_trimmed", "fully_exited"])

# Position for trail stop test
position_with_trail_st = st.fixed_dictionaries({
    "current_price": positive_price_st,
    "trail_stop_level": positive_price_st,
    "direction": direction_st,
})

# Position for capital freed test
position_for_trims_st = st.fixed_dictionaries({
    "trim_status": trim_status_st,
    "size_pct_nav": size_pct_nav_st,
})

# List of positions for capital freed test
positions_list_st = st.lists(position_for_trims_st, min_size=0, max_size=50)


# ---------------------------------------------------------------------------
# Property 3: Trail stop proximity percentage is consistent with price data
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(position=position_with_trail_st)
def test_property_3_trail_stop_proximity_long(position: dict):
    """
    Feature: dashboard-autonomous-revamp, Property 3: Trail stop proximity percentage
    is consistent with price data

    **Validates: Requirements 1.2**

    For a long position, trail stop proximity = (current_price - trail_stop_level) / current_price
    """
    position["direction"] = "long"
    result = compute_trail_stop_proximity(position)

    assert result is not None
    expected = (position["current_price"] - position["trail_stop_level"]) / position["current_price"]
    assert math.isclose(result, expected, rel_tol=1e-9), (
        f"Long trail stop proximity mismatch: got {result}, expected {expected}"
    )


@settings(max_examples=200)
@given(position=position_with_trail_st)
def test_property_3_trail_stop_proximity_short(position: dict):
    """
    Feature: dashboard-autonomous-revamp, Property 3: Trail stop proximity percentage
    is consistent with price data

    **Validates: Requirements 1.2**

    For a short position, trail stop proximity = (trail_stop_level - current_price) / current_price
    """
    position["direction"] = "short"
    result = compute_trail_stop_proximity(position)

    assert result is not None
    expected = (position["trail_stop_level"] - position["current_price"]) / position["current_price"]
    assert math.isclose(result, expected, rel_tol=1e-9), (
        f"Short trail stop proximity mismatch: got {result}, expected {expected}"
    )


@settings(max_examples=100)
@given(position=position_with_trail_st)
def test_property_3_trail_stop_proximity_null_guard(position: dict):
    """
    Feature: dashboard-autonomous-revamp, Property 3: Trail stop proximity percentage
    is consistent with price data

    **Validates: Requirements 1.2**

    When trail_stop_level is None or current_price is falsy, returns None.
    """
    # Test missing trail_stop_level
    pos_no_stop = dict(position)
    pos_no_stop["trail_stop_level"] = None
    assert compute_trail_stop_proximity(pos_no_stop) is None

    # Test missing current_price
    pos_no_price = dict(position)
    pos_no_price["current_price"] = 0
    assert compute_trail_stop_proximity(pos_no_price) is None

    # Test None position
    assert compute_trail_stop_proximity(None) is None


# ---------------------------------------------------------------------------
# Property 4: Factor beta classification respects threshold ordering
# ---------------------------------------------------------------------------

# Severity ordering for monotonicity check
SEVERITY_ORDER = {"green": 0, "amber": 1, "red": 2}


@settings(max_examples=200)
@given(beta=beta_st)
def test_property_4_classification_thresholds(beta: float):
    """
    Feature: dashboard-autonomous-revamp, Property 4: Factor beta classification
    respects threshold ordering

    **Validates: Requirements 3.4**

    classifyFactorBeta(beta) returns "green" when |beta| < 0.4,
    "amber" when 0.4 <= |beta| < 0.6, "red" when |beta| >= 0.6.
    """
    result = classify_factor_beta(beta)
    abs_beta = abs(beta)

    if abs_beta < 0.4:
        assert result == "green", (
            f"Expected 'green' for |beta|={abs_beta} < 0.4, got '{result}'"
        )
    elif abs_beta < 0.6:
        assert result == "amber", (
            f"Expected 'amber' for 0.4 <= |beta|={abs_beta} < 0.6, got '{result}'"
        )
    else:
        assert result == "red", (
            f"Expected 'red' for |beta|={abs_beta} >= 0.6, got '{result}'"
        )


@settings(max_examples=200)
@given(
    beta1=beta_st,
    beta2=beta_st,
)
def test_property_4_monotonicity(beta1: float, beta2: float):
    """
    Feature: dashboard-autonomous-revamp, Property 4: Factor beta classification
    respects threshold ordering

    **Validates: Requirements 3.4**

    The classification is monotonically non-decreasing in severity as |beta| increases.
    If |beta1| <= |beta2|, then severity(classify(beta1)) <= severity(classify(beta2)).
    """
    abs1 = abs(beta1)
    abs2 = abs(beta2)

    result1 = classify_factor_beta(beta1)
    result2 = classify_factor_beta(beta2)

    if abs1 <= abs2:
        assert SEVERITY_ORDER[result1] <= SEVERITY_ORDER[result2], (
            f"Monotonicity violated: |beta1|={abs1} -> {result1}, "
            f"|beta2|={abs2} -> {result2}, but severity should be non-decreasing"
        )


@settings(max_examples=100)
@given(beta=beta_st)
def test_property_4_symmetry(beta: float):
    """
    Feature: dashboard-autonomous-revamp, Property 4: Factor beta classification
    respects threshold ordering

    **Validates: Requirements 3.4**

    Classification is symmetric: classifyFactorBeta(beta) == classifyFactorBeta(-beta).
    """
    result_pos = classify_factor_beta(beta)
    result_neg = classify_factor_beta(-beta)

    assert result_pos == result_neg, (
        f"Asymmetric classification: beta={beta} -> '{result_pos}', "
        f"-beta={-beta} -> '{result_neg}'"
    )


def test_property_4_null_returns_green():
    """
    Feature: dashboard-autonomous-revamp, Property 4: Factor beta classification
    respects threshold ordering

    **Validates: Requirements 3.4**

    classifyFactorBeta(None) returns "green".
    """
    assert classify_factor_beta(None) == "green"


# ---------------------------------------------------------------------------
# Property 5: Capital freed by trims aggregation is non-negative
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(positions=positions_list_st, nav=nav_st)
def test_property_5_capital_freed_non_negative(positions: list[dict], nav: float):
    """
    Feature: dashboard-autonomous-revamp, Property 5: Capital freed by trims
    aggregation is non-negative

    **Validates: Requirements 2.3**

    For any set of positions and positive NAV, computeCapitalFreedByTrims SHALL
    return a non-negative value.
    """
    result = compute_capital_freed_by_trims(positions, nav)
    assert result >= 0, (
        f"Capital freed should be non-negative, got {result} "
        f"with {len(positions)} positions and nav={nav}"
    )


@settings(max_examples=200)
@given(positions=positions_list_st, nav=nav_st)
def test_property_5_capital_freed_formula(positions: list[dict], nav: float):
    """
    Feature: dashboard-autonomous-revamp, Property 5: Capital freed by trims
    aggregation is non-negative

    **Validates: Requirements 2.3**

    The capital freed equals the sum of |size_pct_nav| * nav * 0.5 for all
    half_trimmed positions.
    """
    result = compute_capital_freed_by_trims(positions, nav)

    # Manually compute expected value
    expected = 0.0
    for p in positions:
        if p.get("trim_status") == "half_trimmed":
            expected += abs(p.get("size_pct_nav") or 0) * nav * 0.5

    assert math.isclose(result, expected, rel_tol=1e-9), (
        f"Capital freed mismatch: got {result}, expected {expected}"
    )


@settings(max_examples=100)
@given(positions=positions_list_st)
def test_property_5_zero_or_negative_nav(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 5: Capital freed by trims
    aggregation is non-negative

    **Validates: Requirements 2.3**

    When NAV is zero or negative, computeCapitalFreedByTrims returns 0.
    """
    assert compute_capital_freed_by_trims(positions, 0) == 0
    assert compute_capital_freed_by_trims(positions, -100.0) == 0
    assert compute_capital_freed_by_trims(positions, None) == 0


@settings(max_examples=100)
@given(nav=nav_st)
def test_property_5_empty_positions(nav: float):
    """
    Feature: dashboard-autonomous-revamp, Property 5: Capital freed by trims
    aggregation is non-negative

    **Validates: Requirements 2.3**

    When positions list is empty or None, computeCapitalFreedByTrims returns 0.
    """
    assert compute_capital_freed_by_trims([], nav) == 0
    assert compute_capital_freed_by_trims(None, nav) == 0
