# Feature: operational-reliability, Property 9: Drawdown Progressive Thresholds
"""
Property-based tests for drawdown progressive threshold alerts.

For all (current_nav, session_open_nav) pairs where session_open_nav > 0:
- Compute drawdown = (current_nav - session_open_nav) / session_open_nav
- If drawdown <= -0.04: result should be "emergency"
- If -0.04 < drawdown <= -0.03: result should be "deleverage"
- If drawdown > -0.03: result should be None

Validates: Requirements 15.1, 15.2, 15.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.trading.circuit_breaker import (
    compute_progressive_deleverage,
    DELEVERAGE_THRESHOLD,
    EMERGENCY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# session_open_nav: positive realistic portfolio values
session_open_nav_strategy = st.floats(
    min_value=1000.0, max_value=1_000_000_000.0, allow_nan=False, allow_infinity=False
)

# drawdown_pct: range from -20% to +10% (covers all thresholds with margin)
drawdown_pct_strategy = st.floats(
    min_value=-0.20, max_value=0.10, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Property 9: Drawdown Progressive Thresholds
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(
    session_open_nav=session_open_nav_strategy,
    drawdown_pct=drawdown_pct_strategy,
)
def test_property_9_drawdown_progressive_thresholds(
    session_open_nav: float, drawdown_pct: float
):
    """
    **Validates: Requirements 15.1, 15.2, 15.3**

    Property 9: Drawdown Progressive Thresholds — For all NAV/session_open_nav
    pairs, exactly the correct threshold alert is emitted:
    - drawdown <= -4%: "emergency"
    - -4% < drawdown <= -3%: "deleverage"
    - drawdown > -3%: None
    """
    # Compute current_nav from session_open_nav and drawdown percentage
    current_nav = session_open_nav * (1 + drawdown_pct)

    # Get actual result from the function under test
    result = compute_progressive_deleverage(current_nav, session_open_nav)

    # Compute expected result based on drawdown thresholds
    drawdown = (current_nav - session_open_nav) / session_open_nav

    if drawdown <= EMERGENCY_THRESHOLD:  # <= -0.04
        expected = "emergency"
    elif drawdown <= DELEVERAGE_THRESHOLD:  # <= -0.03
        expected = "deleverage"
    else:
        expected = None

    assert result == expected, (
        f"For session_open_nav={session_open_nav}, current_nav={current_nav}, "
        f"drawdown={drawdown:.6f}: expected '{expected}', got '{result}'"
    )
