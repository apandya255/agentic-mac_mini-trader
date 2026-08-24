"""
Gate Validator — validates pipeline gate conditions for autonomous order booking.

All three gate conditions must pass for an order to be auto-booked:
  1. Conviction score ≥ 5
  2. Risk decision is "approved" or "approved_with_modifications"
  3. PM execute flag is True

If any gate fails, the order is rejected and the first failing gate is identified.
"""

from dataclasses import dataclass


@dataclass
class GateResult:
    """Result of pipeline gate validation."""

    passed: bool
    failing_gate: str | None = None  # "conviction", "risk", or "pm_execute"


def validate_gates(
    conviction: int | float,
    risk_decision: str,
    pm_execute: bool,
) -> GateResult:
    """
    Validate all three pipeline gate conditions.

    Args:
        conviction: Final conviction score from the debate phase.
        risk_decision: Risk gate decision string (e.g. "approved").
        pm_execute: PM decision execute flag.

    Returns:
        GateResult with passed=True if all gates clear,
        or passed=False with the first failing gate identified.
    """
    if conviction < 5:
        return GateResult(passed=False, failing_gate="conviction")
    if risk_decision not in ("approved", "approved_with_modifications"):
        return GateResult(passed=False, failing_gate="risk")
    if not pm_execute:
        return GateResult(passed=False, failing_gate="pm_execute")
    return GateResult(passed=True)
