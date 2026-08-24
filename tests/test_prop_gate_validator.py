# Feature: autonomous-trading-loop, Property 2: Gate validation is conjunction of all three conditions
"""
Property-based tests for src/trading/gate_validator.py — gate validation logic.

Property 2: Gate validation is conjunction of all three conditions
For any order with arbitrary conviction score, risk decision string, and PM execute
boolean, the order SHALL be booked if and only if (conviction >= 5) AND
(risk_decision in {"approved", "approved_with_modifications"}) AND (pm_execute = true).
If any condition fails, the order SHALL be rejected with the specific failing gate
identified.

**Validates: Requirements 1.1, 10.1, 10.2, 10.3, 10.4**
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.trading.gate_validator import GateResult, validate_gates

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Conviction scores: floats covering well below and above the threshold of 5
conviction_strategy = st.floats(min_value=-10.0, max_value=20.0, allow_nan=False, allow_infinity=False)

# Valid risk decisions that should pass the gate
VALID_RISK_DECISIONS = ["approved", "approved_with_modifications"]

# Invalid risk decisions (representative strings that are NOT in the valid set)
INVALID_RISK_DECISIONS = ["denied", "rejected", "pending", "review", "", "APPROVED", "Approved"]

# Risk decision strategy: mix of valid and invalid
risk_decision_strategy = st.one_of(
    st.sampled_from(VALID_RISK_DECISIONS),
    st.sampled_from(INVALID_RISK_DECISIONS),
    st.text(min_size=0, max_size=30),
)

# PM execute: boolean
pm_execute_strategy = st.booleans()


# ---------------------------------------------------------------------------
# Property Test: Gate validation is conjunction of all three conditions
# ---------------------------------------------------------------------------


@given(
    conviction=conviction_strategy,
    risk_decision=risk_decision_strategy,
    pm_execute=pm_execute_strategy,
)
@settings(max_examples=500)
def test_property2_gate_validation_is_conjunction(
    conviction: float, risk_decision: str, pm_execute: bool
):
    """
    **Validates: Requirements 1.1, 10.1, 10.2, 10.3, 10.4**

    Property 2: Gate validation is conjunction of all three conditions.
    result.passed is True iff ALL three conditions are met simultaneously:
      - conviction >= 5
      - risk_decision in {"approved", "approved_with_modifications"}
      - pm_execute is True
    """
    result = validate_gates(conviction, risk_decision, pm_execute)

    # Compute expected outcome from the conjunction of all three conditions
    conviction_ok = conviction >= 5
    risk_ok = risk_decision in ("approved", "approved_with_modifications")
    pm_ok = pm_execute is True

    all_pass = conviction_ok and risk_ok and pm_ok

    # Core property: passed iff all three conditions hold
    assert result.passed == all_pass, (
        f"Expected passed={all_pass} but got passed={result.passed} "
        f"for conviction={conviction}, risk_decision={risk_decision!r}, pm_execute={pm_execute}"
    )

    # When passed, there should be no failing gate
    if result.passed:
        assert result.failing_gate is None, (
            f"Gate passed but failing_gate is {result.failing_gate!r}"
        )
    else:
        # When failed, a specific failing gate must be identified
        assert result.failing_gate is not None, (
            "Gate failed but failing_gate is None"
        )
        assert result.failing_gate in ("conviction", "risk", "pm_execute"), (
            f"Unexpected failing_gate value: {result.failing_gate!r}"
        )

        # Verify the reported failing gate is actually failing
        if result.failing_gate == "conviction":
            assert not conviction_ok, (
                f"Reported conviction failure but conviction={conviction} >= 5"
            )
        elif result.failing_gate == "risk":
            assert not risk_ok, (
                f"Reported risk failure but risk_decision={risk_decision!r} is valid"
            )
        elif result.failing_gate == "pm_execute":
            assert not pm_ok, (
                f"Reported pm_execute failure but pm_execute={pm_execute} is True"
            )
