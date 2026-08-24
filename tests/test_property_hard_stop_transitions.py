# Feature: operational-reliability, Property 8: Hard Stop State Transition Validity
"""
Property-based test for hard stop state transition validity.

Property 8: For all positions with trim_status in {"untrimmed", "half_trimmed"} that
trigger a stop breach, the position SHALL end up with trim_status == "fully_exited"
after auto_close_stopped_positions() runs.

Valid trim_status transitions:
  - "untrimmed" → "half_trimmed" → "fully_exited"
  - "untrimmed" → "fully_exited" (direct close without trim)

**Validates: Requirements 8.1**
"""

import os
import sys
from pathlib import Path

# Ensure project root and src are on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from monitor import auto_close_stopped_positions, Alert
import monitor as _monitor_module
from src.trading.position_states import transition, is_valid_transition, VALID_TRANSITIONS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid starting trim_status values for positions that can reach "fully_exited"
valid_start_trim_status = st.sampled_from(["untrimmed", "half_trimmed"])

# Strategy for current price (positive)
current_price_strategy = st.floats(
    min_value=1.0,
    max_value=10000.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for combined P&L percentage (negative, since stop is triggered)
combined_pnl_strategy = st.floats(
    min_value=-0.99,
    max_value=-0.001,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for position size
size_pct_nav_strategy = st.floats(
    min_value=0.001,
    max_value=0.10,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for direction
direction_strategy = st.sampled_from(["long", "short"])

# Strategy for ticker names
ticker_strategy = st.text(
    min_size=1,
    max_size=5,
    alphabet=st.characters(whitelist_categories=("Lu",)),
)


# ---------------------------------------------------------------------------
# Property 8: Hard Stop State Transition Validity
# ---------------------------------------------------------------------------


@given(
    trim_status=valid_start_trim_status,
    current_price=current_price_strategy,
    combined_pnl_pct=combined_pnl_strategy,
    size_pct_nav=size_pct_nav_strategy,
    direction=direction_strategy,
    ticker=ticker_strategy,
)
@settings(max_examples=100)
def test_property8_stop_triggered_positions_reach_fully_exited(
    trim_status: str,
    current_price: float,
    combined_pnl_pct: float,
    size_pct_nav: float,
    direction: str,
    ticker: str,
):
    """
    **Validates: Requirements 8.1**

    Property 8: For all positions with trim_status in {"untrimmed", "half_trimmed"}
    that trigger a stop breach, the position SHALL end up with trim_status ==
    "fully_exited" after auto_close_stopped_positions() runs.

    The state machine transition must go through a valid path only:
      untrimmed → fully_exited
      half_trimmed → fully_exited
    """
    # Ensure the mock price_service returns "ok" for this ticker
    _monitor_module.price_service.fetch_status[ticker] = "ok"

    try:
        pos = {
            "ticker": ticker,
            "status": "active",
            "stop_triggered": True,
            "current_price": current_price,
            "combined_pnl_pct": combined_pnl_pct,
            "direction": direction,
            "size_pct_nav": size_pct_nav,
            "trim_status": trim_status,
        }
        book = {
            "nav": 10_000_000,
            "cash_pct": 0.50,
            "positions": [pos],
            "trade_journal": [],
        }
        alerts = []

        # Run auto_close_stopped_positions
        closed_count = auto_close_stopped_positions(book, alerts)

        # The position must be closed
        assert closed_count == 1, (
            f"Expected 1 position closed, got {closed_count}"
        )

        # trim_status must be "fully_exited" after stop breach
        assert pos["trim_status"] == "fully_exited", (
            f"Position with initial trim_status='{trim_status}' should transition to "
            f"'fully_exited' after stop breach, but got '{pos['trim_status']}'"
        )

        # Verify the transition was valid according to state machine
        assert is_valid_transition(trim_status, "fully_exited"), (
            f"Transition {trim_status} → fully_exited is not valid in state machine"
        )
    finally:
        _monitor_module.price_service.fetch_status.pop(ticker, None)


@given(
    trim_status=valid_start_trim_status,
    ticker=ticker_strategy,
)
@settings(max_examples=100)
def test_property8_transition_does_not_raise_for_valid_start_states(
    trim_status: str,
    ticker: str,
):
    """
    **Validates: Requirements 8.1**

    Property 8 (supplementary): For all valid starting states that can reach
    "fully_exited", the transition() function SHALL NOT raise ValueError.
    This confirms the state machine allows direct stop-breach closure from
    both "untrimmed" and "half_trimmed".
    """
    pos = {"ticker": ticker, "trim_status": trim_status}

    # This should not raise — valid forward transition
    result = transition(pos, "fully_exited")

    assert result["trim_status"] == "fully_exited", (
        f"transition() from '{trim_status}' to 'fully_exited' should set "
        f"trim_status to 'fully_exited', got '{result['trim_status']}'"
    )


@given(
    ticker=ticker_strategy,
    current_price=current_price_strategy,
    combined_pnl_pct=combined_pnl_strategy,
    size_pct_nav=size_pct_nav_strategy,
    direction=direction_strategy,
)
@settings(max_examples=100)
def test_property8_fully_exited_positions_handled_gracefully(
    ticker: str,
    current_price: float,
    combined_pnl_pct: float,
    size_pct_nav: float,
    direction: str,
):
    """
    **Validates: Requirements 8.1**

    Property 8 (invalid start state): For positions already in "fully_exited"
    state that somehow trigger a stop breach, the system SHALL handle gracefully
    without raising an exception. The trim_status remains "fully_exited".

    Note: "fully_exited" → "fully_exited" is NOT a valid state machine transition,
    but auto_close_stopped_positions catches the ValueError and sets trim_status
    directly as a fallback.
    """
    _monitor_module.price_service.fetch_status[ticker] = "ok"

    try:
        pos = {
            "ticker": ticker,
            "status": "active",
            "stop_triggered": True,
            "current_price": current_price,
            "combined_pnl_pct": combined_pnl_pct,
            "direction": direction,
            "size_pct_nav": size_pct_nav,
            "trim_status": "fully_exited",
        }
        book = {
            "nav": 10_000_000,
            "cash_pct": 0.50,
            "positions": [pos],
            "trade_journal": [],
        }
        alerts = []

        # Should NOT raise even though fully_exited → fully_exited is invalid
        closed_count = auto_close_stopped_positions(book, alerts)

        # Position is still closed (the function proceeds)
        assert pos["status"] == "closed", (
            f"Position should be closed even with invalid initial trim_status"
        )
        # trim_status should remain "fully_exited" (set directly in the except block)
        assert pos["trim_status"] == "fully_exited", (
            f"trim_status should be 'fully_exited' after graceful handling, "
            f"got '{pos['trim_status']}'"
        )
    finally:
        _monitor_module.price_service.fetch_status.pop(ticker, None)
