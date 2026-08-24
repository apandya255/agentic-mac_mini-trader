"""
Property-based tests for the position trim-status state machine.

Property 8: Trim status state machine only moves forward.
Only valid transitions: untrimmed → half_trimmed → fully_exited
(plus untrimmed → fully_exited for stop-loss/thesis-break closures).
Backward transitions always raise ValueError; forward transitions always succeed.

**Validates: Requirements 4.4**
"""

import os
import sys

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.position_states import (
    VALID_TRANSITIONS,
    is_valid_transition,
    transition,
)

# All defined states in the state machine
ALL_STATES = list(VALID_TRANSITIONS.keys())

# Define forward (valid) transition pairs
FORWARD_TRANSITIONS = [
    ("untrimmed", "half_trimmed"),
    ("untrimmed", "fully_exited"),
    ("half_trimmed", "fully_exited"),
]

# Define backward (invalid) transition pairs — going against the forward flow
BACKWARD_TRANSITIONS = [
    ("half_trimmed", "untrimmed"),
    ("fully_exited", "untrimmed"),
    ("fully_exited", "half_trimmed"),
]

# Self-transitions are also invalid (no staying in the same state)
SELF_TRANSITIONS = [
    ("untrimmed", "untrimmed"),
    ("half_trimmed", "half_trimmed"),
    ("fully_exited", "fully_exited"),
]


# ---------------------------------------------------------------------------
# Property 8: Trim status state machine only moves forward
# ---------------------------------------------------------------------------
# **Validates: Requirements 4.4**


@given(
    transition_pair=st.sampled_from(FORWARD_TRANSITIONS),
    ticker=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("Lu",))),
)
@settings(max_examples=200)
def test_property8_forward_transitions_always_succeed(transition_pair, ticker):
    """
    Property 8 (forward): For any valid forward transition in the state machine,
    transition() SHALL succeed and update trim_status to the target state.

    Valid forward transitions:
      untrimmed → half_trimmed
      untrimmed → fully_exited
      half_trimmed → fully_exited
    """
    from_state, to_state = transition_pair
    position = {"ticker": ticker, "trim_status": from_state}

    result = transition(position, to_state)

    # The transition must succeed and set the new state
    assert result["trim_status"] == to_state, (
        f"Forward transition {from_state} → {to_state} should succeed, "
        f"but trim_status is {result['trim_status']}"
    )
    # The returned dict is the same reference (mutation)
    assert result is position


@given(
    transition_pair=st.sampled_from(BACKWARD_TRANSITIONS),
    ticker=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("Lu",))),
)
@settings(max_examples=200)
def test_property8_backward_transitions_always_raise(transition_pair, ticker):
    """
    Property 8 (backward): For any backward transition attempt,
    transition() SHALL raise ValueError. The state machine only moves forward.

    Invalid backward transitions:
      half_trimmed → untrimmed
      fully_exited → untrimmed
      fully_exited → half_trimmed
    """
    from_state, to_state = transition_pair
    position = {"ticker": ticker, "trim_status": from_state}

    with pytest.raises(ValueError, match="Invalid transition"):
        transition(position, to_state)

    # The position must remain unchanged after a failed transition
    assert position["trim_status"] == from_state, (
        f"Position trim_status should remain {from_state} after failed backward transition"
    )


@given(
    state=st.sampled_from(ALL_STATES),
    ticker=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("Lu",))),
)
@settings(max_examples=200)
def test_property8_self_transitions_always_raise(state, ticker):
    """
    Property 8 (self): Transitioning to the same state is not valid.
    The state machine requires forward progress only.
    """
    position = {"ticker": ticker, "trim_status": state}

    with pytest.raises(ValueError, match="Invalid transition"):
        transition(position, state)

    # Position unchanged
    assert position["trim_status"] == state


@given(
    from_state=st.sampled_from(ALL_STATES),
    to_state=st.sampled_from(ALL_STATES),
)
@settings(max_examples=300)
def test_property8_is_valid_transition_matches_forward_only(from_state, to_state):
    """
    Property 8 (consistency): is_valid_transition returns True if and only if
    the (from_state, to_state) pair is a forward transition in the state machine.
    """
    expected_valid = (from_state, to_state) in FORWARD_TRANSITIONS
    actual_valid = is_valid_transition(from_state, to_state)

    assert actual_valid == expected_valid, (
        f"is_valid_transition({from_state}, {to_state}) returned {actual_valid}, "
        f"expected {expected_valid}"
    )


@given(
    invalid_state=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in ALL_STATES
    ),
    valid_state=st.sampled_from(ALL_STATES),
)
@settings(max_examples=200)
def test_property8_unknown_states_are_never_valid(invalid_state, valid_state):
    """
    Property 8 (unknown states): Transitions from or to unknown states are
    never valid. The state machine is closed over its three defined states.
    """
    # Unknown → any valid state: always invalid
    assert is_valid_transition(invalid_state, valid_state) is False, (
        f"Transition from unknown state '{invalid_state}' to '{valid_state}' should be invalid"
    )

    # Any valid state → unknown: always invalid
    assert is_valid_transition(valid_state, invalid_state) is False, (
        f"Transition from '{valid_state}' to unknown state '{invalid_state}' should be invalid"
    )


@given(
    invalid_to_state=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in ALL_STATES
    ),
    from_state=st.sampled_from(ALL_STATES),
    ticker=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("Lu",))),
)
@settings(max_examples=200)
def test_property8_transition_to_unknown_state_raises(invalid_to_state, from_state, ticker):
    """
    Property 8 (unknown target): Attempting to transition to a state not in the
    state machine always raises ValueError.
    """
    position = {"ticker": ticker, "trim_status": from_state}

    with pytest.raises(ValueError, match="Invalid transition"):
        transition(position, invalid_to_state)

    # Position must remain unchanged
    assert position["trim_status"] == from_state
