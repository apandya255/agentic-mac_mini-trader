"""
Property-based tests for exposure computation functions.

Feature: dashboard-autonomous-revamp

Property 1: Gross exposure is the sum of absolute position sizes
Property 2: Net exposure is the signed sum of position sizes

**Validates: Requirements 2.2**

These tests verify Python equivalents of the client-side JavaScript
computeGrossExposure and computeNetExposure functions defined in dashboard.py.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Python equivalents of JS computation functions (from dashboard.py)
# ---------------------------------------------------------------------------


def compute_gross_exposure(positions: list[dict] | None) -> float:
    """
    Python equivalent of:
        function computeGrossExposure(positions) {
            return (positions || []).reduce(
                (sum, p) => sum + Math.abs(p.size_pct_nav || 0), 0);
        }
    """
    if not positions:
        return 0.0
    return sum(abs(p.get("size_pct_nav") or 0) for p in positions)


def compute_net_exposure(positions: list[dict] | None) -> float:
    """
    Python equivalent of:
        function computeNetExposure(positions) {
            return (positions || []).reduce((sum, p) => {
                const size = Math.abs(p.size_pct_nav || 0);
                const dir = (p.direction || 'long').toLowerCase();
                return sum + (dir === 'short' ? -size : size);
            }, 0);
        }
    """
    if not positions:
        return 0.0
    total = 0.0
    for p in positions:
        size = abs(p.get("size_pct_nav") or 0)
        direction = (p.get("direction") or "long").lower()
        if direction == "short":
            total -= size
        else:
            total += size
    return total


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# size_pct_nav as a percentage of NAV — realistic range from 0% to 50%
size_pct_nav_st = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
)

# Direction — only "long" or "short" per the data model
direction_st = st.sampled_from(["long", "short"])

# A single position dict with size_pct_nav and direction
position_st = st.fixed_dictionaries(
    {"size_pct_nav": size_pct_nav_st, "direction": direction_st}
)

# List of positions — 0 to 50 positions
positions_st = st.lists(position_st, min_size=0, max_size=50)


# ---------------------------------------------------------------------------
# Property 1: Gross exposure is the sum of absolute position sizes
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(positions=positions_st)
def test_property_1_gross_exposure_equals_sum_of_absolutes(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 1: Gross exposure is the sum of absolute position sizes

    **Validates: Requirements 2.2**

    For any set of active positions with size_pct_nav values,
    computeGrossExposure(positions) SHALL equal the sum of absolute values
    of all size_pct_nav fields.
    """
    result = compute_gross_exposure(positions)
    expected = sum(abs(p["size_pct_nav"]) for p in positions)

    assert abs(result - expected) < 1e-9, (
        f"Gross exposure mismatch: got {result}, expected {expected}"
    )


@settings(max_examples=200)
@given(positions=positions_st)
def test_property_1_gross_exposure_is_non_negative(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 1: Gross exposure is the sum of absolute position sizes

    **Validates: Requirements 2.2**

    Gross exposure (sum of absolute values) SHALL always be non-negative
    regardless of position directions or sign of size_pct_nav.
    """
    result = compute_gross_exposure(positions)
    assert result >= 0.0, f"Gross exposure should be non-negative, got {result}"


def test_property_1_gross_exposure_empty_positions():
    """
    Feature: dashboard-autonomous-revamp, Property 1: Gross exposure is the sum of absolute position sizes

    **Validates: Requirements 2.2**

    Gross exposure of an empty list or None SHALL be 0.
    """
    assert compute_gross_exposure([]) == 0.0
    assert compute_gross_exposure(None) == 0.0


# ---------------------------------------------------------------------------
# Property 2: Net exposure is the signed sum of position sizes
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(positions=positions_st)
def test_property_2_net_exposure_equals_signed_sum(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    For any set of active positions with size_pct_nav and direction fields,
    computeNetExposure(positions) SHALL equal the sum of size_pct_nav
    (positive for long, negative for short).
    """
    result = compute_net_exposure(positions)

    # Compute expected: positive for long, negative for short
    expected = 0.0
    for p in positions:
        size = abs(p["size_pct_nav"])
        direction = p["direction"].lower()
        if direction == "short":
            expected -= size
        else:
            expected += size

    assert abs(result - expected) < 1e-9, (
        f"Net exposure mismatch: got {result}, expected {expected}"
    )


@settings(max_examples=200)
@given(positions=positions_st)
def test_property_2_net_exposure_bounded_by_gross(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    The absolute value of net exposure SHALL never exceed gross exposure.
    |net_exposure| <= gross_exposure always holds.
    """
    gross = compute_gross_exposure(positions)
    net = compute_net_exposure(positions)

    assert abs(net) <= gross + 1e-9, (
        f"|net_exposure| ({abs(net)}) > gross_exposure ({gross})"
    )


def test_property_2_net_exposure_empty_positions():
    """
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    Net exposure of an empty list or None SHALL be 0.
    """
    assert compute_net_exposure([]) == 0.0
    assert compute_net_exposure(None) == 0.0


@settings(max_examples=200)
@given(
    size=st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False)
)
def test_property_2_all_long_net_equals_gross(size: float):
    """
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    When all positions are long, net exposure SHALL equal gross exposure.
    """
    positions = [
        {"size_pct_nav": size, "direction": "long"},
        {"size_pct_nav": size * 0.5, "direction": "long"},
    ]
    gross = compute_gross_exposure(positions)
    net = compute_net_exposure(positions)

    assert abs(net - gross) < 1e-9, (
        f"All-long portfolio: net ({net}) should equal gross ({gross})"
    )


@settings(max_examples=200)
@given(
    size=st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False)
)
def test_property_2_all_short_net_equals_negative_gross(size: float):
    """
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    When all positions are short, net exposure SHALL equal -gross exposure.
    """
    positions = [
        {"size_pct_nav": size, "direction": "short"},
        {"size_pct_nav": size * 0.5, "direction": "short"},
    ]
    gross = compute_gross_exposure(positions)
    net = compute_net_exposure(positions)

    assert abs(net - (-gross)) < 1e-9, (
        f"All-short portfolio: net ({net}) should equal -gross ({-gross})"
    )


# ---------------------------------------------------------------------------
# Edge cases: positions with missing/None size_pct_nav or direction
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    positions=st.lists(
        st.fixed_dictionaries(
            {
                "size_pct_nav": st.one_of(size_pct_nav_st, st.none()),
                "direction": st.one_of(direction_st, st.none(), st.just("")),
            }
        ),
        min_size=0,
        max_size=30,
    )
)
def test_property_1_2_handles_missing_fields_gracefully(positions: list[dict]):
    """
    Feature: dashboard-autonomous-revamp, Property 1: Gross exposure is the sum of absolute position sizes
    Feature: dashboard-autonomous-revamp, Property 2: Net exposure is the signed sum of position sizes

    **Validates: Requirements 2.2**

    Both functions SHALL handle None/missing size_pct_nav (treated as 0)
    and None/empty direction (treated as 'long') without raising exceptions.
    """
    # Should not raise any exception
    gross = compute_gross_exposure(positions)
    net = compute_net_exposure(positions)

    # Basic sanity: gross is always non-negative, |net| <= gross
    assert gross >= 0.0
    assert abs(net) <= gross + 1e-9
