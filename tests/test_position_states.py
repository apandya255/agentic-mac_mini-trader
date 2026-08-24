"""
Unit tests for the position trim-status state machine.

Validates: Requirements 4.4
"""

import os
import sys

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.position_states import (
    VALID_TRANSITIONS,
    is_valid_transition,
    transition,
)


# ---------------------------------------------------------------------------
# Tests for VALID_TRANSITIONS structure
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Verify the VALID_TRANSITIONS dict is correctly defined."""

    def test_untrimmed_can_go_to_half_trimmed(self):
        assert "half_trimmed" in VALID_TRANSITIONS["untrimmed"]

    def test_untrimmed_can_go_to_fully_exited(self):
        assert "fully_exited" in VALID_TRANSITIONS["untrimmed"]

    def test_half_trimmed_can_go_to_fully_exited(self):
        assert "fully_exited" in VALID_TRANSITIONS["half_trimmed"]

    def test_fully_exited_has_no_transitions(self):
        assert VALID_TRANSITIONS["fully_exited"] == []

    def test_all_states_present(self):
        assert set(VALID_TRANSITIONS.keys()) == {
            "untrimmed",
            "half_trimmed",
            "fully_exited",
        }


# ---------------------------------------------------------------------------
# Tests for is_valid_transition
# ---------------------------------------------------------------------------


class TestIsValidTransition:
    """Verify is_valid_transition returns correct booleans."""

    def test_untrimmed_to_half_trimmed_valid(self):
        assert is_valid_transition("untrimmed", "half_trimmed") is True

    def test_untrimmed_to_fully_exited_valid(self):
        assert is_valid_transition("untrimmed", "fully_exited") is True

    def test_half_trimmed_to_fully_exited_valid(self):
        assert is_valid_transition("half_trimmed", "fully_exited") is True

    def test_half_trimmed_to_untrimmed_invalid(self):
        assert is_valid_transition("half_trimmed", "untrimmed") is False

    def test_fully_exited_to_untrimmed_invalid(self):
        assert is_valid_transition("fully_exited", "untrimmed") is False

    def test_fully_exited_to_half_trimmed_invalid(self):
        assert is_valid_transition("fully_exited", "half_trimmed") is False

    def test_unknown_from_state_returns_false(self):
        assert is_valid_transition("nonexistent", "half_trimmed") is False

    def test_same_state_transition_invalid(self):
        assert is_valid_transition("untrimmed", "untrimmed") is False
        assert is_valid_transition("half_trimmed", "half_trimmed") is False
        assert is_valid_transition("fully_exited", "fully_exited") is False


# ---------------------------------------------------------------------------
# Tests for transition
# ---------------------------------------------------------------------------


class TestTransition:
    """Verify transition updates position dict and raises on invalid."""

    def test_untrimmed_to_half_trimmed(self):
        pos = {"ticker": "AAPL", "trim_status": "untrimmed"}
        result = transition(pos, "half_trimmed")
        assert result["trim_status"] == "half_trimmed"
        # Mutates in place
        assert pos["trim_status"] == "half_trimmed"

    def test_untrimmed_to_fully_exited(self):
        pos = {"ticker": "MSFT", "trim_status": "untrimmed"}
        result = transition(pos, "fully_exited")
        assert result["trim_status"] == "fully_exited"

    def test_half_trimmed_to_fully_exited(self):
        pos = {"ticker": "GOOG", "trim_status": "half_trimmed"}
        result = transition(pos, "fully_exited")
        assert result["trim_status"] == "fully_exited"

    def test_invalid_backward_transition_raises(self):
        pos = {"ticker": "TSLA", "trim_status": "half_trimmed"}
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(pos, "untrimmed")

    def test_invalid_from_fully_exited_raises(self):
        pos = {"ticker": "AMZN", "trim_status": "fully_exited"}
        with pytest.raises(ValueError, match="Invalid transition"):
            transition(pos, "half_trimmed")

    def test_missing_trim_status_defaults_to_untrimmed(self):
        pos = {"ticker": "META"}
        result = transition(pos, "half_trimmed")
        assert result["trim_status"] == "half_trimmed"

    def test_missing_trim_status_direct_to_fully_exited(self):
        pos = {"ticker": "NFLX"}
        result = transition(pos, "fully_exited")
        assert result["trim_status"] == "fully_exited"

    def test_returns_same_dict_reference(self):
        pos = {"ticker": "SPY", "trim_status": "untrimmed"}
        result = transition(pos, "half_trimmed")
        assert result is pos

    def test_preserves_other_position_fields(self):
        pos = {
            "ticker": "NVDA",
            "trim_status": "untrimmed",
            "direction": "long",
            "size_pct_nav": 0.03,
            "conviction": 7,
        }
        transition(pos, "half_trimmed")
        assert pos["ticker"] == "NVDA"
        assert pos["direction"] == "long"
        assert pos["size_pct_nav"] == 0.03
        assert pos["conviction"] == 7
