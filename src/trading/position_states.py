"""
Position trim-status state machine.

Manages the trim_status field on positions with valid forward-only transitions:
  untrimmed → half_trimmed → fully_exited
  untrimmed → fully_exited (direct close via stop-loss or thesis-break)

Requirements: 4.4
"""

VALID_TRANSITIONS: dict[str, list[str]] = {
    "untrimmed": ["half_trimmed", "fully_exited"],
    "half_trimmed": ["fully_exited"],
    "fully_exited": [],
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """Check if a trim_status transition is valid.

    Args:
        from_state: Current trim_status value.
        to_state: Desired trim_status value.

    Returns:
        True if the transition is allowed, False otherwise.
    """
    return to_state in VALID_TRANSITIONS.get(from_state, [])


def transition(position: dict, to_state: str) -> dict:
    """Apply a trim_status transition to a position.

    Mutates the position dict in place and also returns it for convenience.

    Args:
        position: A position dict containing at least a 'trim_status' key
                  (defaults to 'untrimmed' if missing).
        to_state: The target trim_status value.

    Returns:
        The updated position dict.

    Raises:
        ValueError: If the requested transition is not valid from the
                    position's current trim_status.
    """
    current = position.get("trim_status", "untrimmed")
    if not is_valid_transition(current, to_state):
        raise ValueError(
            f"Invalid transition: {current} \u2192 {to_state}"
        )
    position["trim_status"] = to_state
    return position
