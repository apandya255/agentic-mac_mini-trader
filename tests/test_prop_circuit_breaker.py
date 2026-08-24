# Feature: autonomous-trading-loop, Property 3: Circuit breaker activates at exactly the -2% threshold
"""
Property-based tests for src/trading/circuit_breaker.py

Property 3: Circuit breaker activates at exactly the -2% threshold
For any pair of current NAV and session-open NAV values where session_open_nav > 0,
the circuit breaker SHALL be active if and only if
(current_nav - session_open_nav) / session_open_nav <= -0.02.

**Validates: Requirements 2.1, 2.2**
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.trading.circuit_breaker import (
    DRAWDOWN_THRESHOLD,
    compute_intraday_drawdown,
    is_circuit_breaker_active,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for session_open_nav: positive floats (must be > 0 for valid drawdown calc)
session_open_nav_strategy = st.floats(
    min_value=0.01,
    max_value=1e12,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for current_nav: any reasonable float (can be positive or zero)
current_nav_strategy = st.floats(
    min_value=0.0,
    max_value=1e12,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for session_open_nav that is <= 0 (edge case)
non_positive_session_nav_strategy = st.floats(
    min_value=-1e12,
    max_value=0.0,
    allow_nan=False,
    allow_infinity=False,
)


# ---------------------------------------------------------------------------
# Property 3: Circuit breaker activates at exactly the -2% threshold
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(
    current_nav=current_nav_strategy,
    session_open_nav=session_open_nav_strategy,
)
def test_property_3_circuit_breaker_active_iff_drawdown_exceeds_threshold(
    current_nav: float, session_open_nav: float
):
    """
    **Validates: Requirements 2.1, 2.2**

    Property 3: For any session_open_nav > 0, the circuit breaker is active
    if and only if (current_nav - session_open_nav) / session_open_nav <= -0.02.
    """
    # Compute the expected drawdown independently
    expected_drawdown = (current_nav - session_open_nav) / session_open_nav
    expected_active = expected_drawdown <= DRAWDOWN_THRESHOLD

    # Get the actual circuit breaker state
    state = is_circuit_breaker_active(current_nav, session_open_nav)

    # The active flag must match our independent calculation
    assert state.active == expected_active, (
        f"Circuit breaker active mismatch: "
        f"current_nav={current_nav}, session_open_nav={session_open_nav}, "
        f"drawdown={expected_drawdown}, expected_active={expected_active}, "
        f"got_active={state.active}"
    )


@settings(max_examples=500)
@given(
    current_nav=current_nav_strategy,
    session_open_nav=session_open_nav_strategy,
)
def test_property_3_drawdown_computation_matches_formula(
    current_nav: float, session_open_nav: float
):
    """
    **Validates: Requirements 2.1, 2.2**

    Property 3 (sub-property): The reported current_drawdown in
    CircuitBreakerState matches the formula (current_nav - session_open_nav) / session_open_nav.
    """
    expected_drawdown = (current_nav - session_open_nav) / session_open_nav

    state = is_circuit_breaker_active(current_nav, session_open_nav)

    assert state.current_drawdown == expected_drawdown, (
        f"Drawdown mismatch: expected={expected_drawdown}, got={state.current_drawdown}"
    )


@settings(max_examples=200)
@given(
    current_nav=current_nav_strategy,
    session_open_nav=non_positive_session_nav_strategy,
)
def test_property_3_non_positive_session_nav_always_inactive(
    current_nav: float, session_open_nav: float
):
    """
    **Validates: Requirements 2.1, 2.2**

    Property 3 (edge case): When session_open_nav <= 0, the circuit breaker
    SHALL always be inactive (drawdown returns 0.0, which does not breach the threshold).
    """
    state = is_circuit_breaker_active(current_nav, session_open_nav)

    assert state.active is False, (
        f"Circuit breaker should be inactive for session_open_nav={session_open_nav}, "
        f"but got active=True"
    )
    assert state.current_drawdown == 0.0, (
        f"Drawdown should be 0.0 for session_open_nav={session_open_nav}, "
        f"got {state.current_drawdown}"
    )


@settings(max_examples=300)
@given(
    session_open_nav=session_open_nav_strategy,
    loss_fraction=st.floats(
        min_value=0.02,
        max_value=0.99,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_3_loss_at_or_beyond_threshold_activates(
    session_open_nav: float, loss_fraction: float
):
    """
    **Validates: Requirements 2.1, 2.2**

    Property 3 (targeted): For any session_open_nav > 0 and loss_fraction >= 0.02,
    current_nav = session_open_nav * (1 - loss_fraction) should activate the breaker,
    provided the actual computed drawdown indeed breaches the threshold.
    """
    current_nav = session_open_nav * (1 - loss_fraction)

    # Due to floating-point arithmetic, verify the actual drawdown meets threshold
    actual_drawdown = (current_nav - session_open_nav) / session_open_nav
    assume(actual_drawdown <= DRAWDOWN_THRESHOLD)

    state = is_circuit_breaker_active(current_nav, session_open_nav)

    assert state.active is True, (
        f"Circuit breaker should be active for drawdown={actual_drawdown} "
        f"(threshold is {DRAWDOWN_THRESHOLD}), but got active=False. "
        f"current_nav={current_nav}, session_open_nav={session_open_nav}"
    )


@settings(max_examples=300)
@given(
    session_open_nav=session_open_nav_strategy,
    loss_fraction=st.floats(
        min_value=0.0,
        max_value=0.019999,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_3_loss_below_threshold_does_not_activate(
    session_open_nav: float, loss_fraction: float
):
    """
    **Validates: Requirements 2.1, 2.2**

    Property 3 (targeted): For any session_open_nav > 0 and loss_fraction < 0.02,
    current_nav = session_open_nav * (1 - loss_fraction) should NOT activate the breaker.
    """
    current_nav = session_open_nav * (1 - loss_fraction)

    # Compute actual drawdown to verify we're indeed below threshold
    drawdown = (current_nav - session_open_nav) / session_open_nav
    assume(drawdown > DRAWDOWN_THRESHOLD)

    state = is_circuit_breaker_active(current_nav, session_open_nav)

    assert state.active is False, (
        f"Circuit breaker should NOT be active for {loss_fraction*100:.4f}% loss "
        f"(threshold is 2%), but got active=True. "
        f"current_nav={current_nav}, session_open_nav={session_open_nav}, "
        f"drawdown={drawdown}"
    )
