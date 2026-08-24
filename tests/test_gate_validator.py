"""
Unit tests for the gate validator module (src/trading/gate_validator.py).

Validates Requirements 10.1, 10.2, 10.3, 10.4.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.gate_validator import GateResult, validate_gates


class TestGateResult:
    """Tests for the GateResult dataclass."""

    def test_passed_result(self):
        result = GateResult(passed=True)
        assert result.passed is True
        assert result.failing_gate is None

    def test_failed_result_with_gate(self):
        result = GateResult(passed=False, failing_gate="conviction")
        assert result.passed is False
        assert result.failing_gate == "conviction"

    def test_default_failing_gate_is_none(self):
        result = GateResult(passed=True)
        assert result.failing_gate is None


class TestValidateGates:
    """Tests for the validate_gates function."""

    def test_all_gates_pass(self):
        """All conditions met — order should be booked."""
        result = validate_gates(conviction=7, risk_decision="approved", pm_execute=True)
        assert result.passed is True
        assert result.failing_gate is None

    def test_all_gates_pass_with_modifications(self):
        """Risk decision 'approved_with_modifications' is also valid."""
        result = validate_gates(
            conviction=5, risk_decision="approved_with_modifications", pm_execute=True
        )
        assert result.passed is True
        assert result.failing_gate is None

    def test_conviction_exactly_5_passes(self):
        """Conviction of exactly 5 meets the ≥ 5 threshold."""
        result = validate_gates(conviction=5, risk_decision="approved", pm_execute=True)
        assert result.passed is True

    def test_conviction_below_threshold_fails(self):
        """Conviction < 5 should fail with 'conviction' gate."""
        result = validate_gates(conviction=4, risk_decision="approved", pm_execute=True)
        assert result.passed is False
        assert result.failing_gate == "conviction"

    def test_conviction_zero_fails(self):
        result = validate_gates(conviction=0, risk_decision="approved", pm_execute=True)
        assert result.passed is False
        assert result.failing_gate == "conviction"

    def test_risk_decision_denied_fails(self):
        """Non-approved risk decision should fail with 'risk' gate."""
        result = validate_gates(conviction=7, risk_decision="denied", pm_execute=True)
        assert result.passed is False
        assert result.failing_gate == "risk"

    def test_risk_decision_empty_string_fails(self):
        result = validate_gates(conviction=7, risk_decision="", pm_execute=True)
        assert result.passed is False
        assert result.failing_gate == "risk"

    def test_pm_execute_false_fails(self):
        """PM execute = False should fail with 'pm_execute' gate."""
        result = validate_gates(conviction=7, risk_decision="approved", pm_execute=False)
        assert result.passed is False
        assert result.failing_gate == "pm_execute"

    def test_first_failing_gate_is_conviction(self):
        """When multiple gates fail, conviction is checked first."""
        result = validate_gates(conviction=3, risk_decision="denied", pm_execute=False)
        assert result.passed is False
        assert result.failing_gate == "conviction"

    def test_first_failing_gate_is_risk_when_conviction_passes(self):
        """When conviction passes but risk fails, 'risk' is reported."""
        result = validate_gates(conviction=8, risk_decision="rejected", pm_execute=False)
        assert result.passed is False
        assert result.failing_gate == "risk"

    def test_float_conviction_at_threshold(self):
        """Float conviction values are supported — 5.0 passes."""
        result = validate_gates(conviction=5.0, risk_decision="approved", pm_execute=True)
        assert result.passed is True

    def test_float_conviction_below_threshold(self):
        """Float conviction 4.9 fails."""
        result = validate_gates(conviction=4.9, risk_decision="approved", pm_execute=True)
        assert result.passed is False
        assert result.failing_gate == "conviction"
