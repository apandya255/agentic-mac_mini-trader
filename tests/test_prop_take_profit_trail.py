"""
Property-based tests for take-profit trim and trail stop logic in monitor.py.

Property 6: Take-profit trim halves position and sets trail stop.
Property 7: Trail stop closure fully exits the remainder.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from monitor import (
    should_trim,
    compute_trail_stop_level,
    ratchet_trail_stop,
    should_trail_stop_close,
    execute_trim,
    execute_trail_stop_close,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic market prices
positive_price = st.floats(min_value=1.0, max_value=100_000.0, allow_nan=False, allow_infinity=False)

# Position size as fraction of NAV (typically 1-10%)
position_size = st.floats(min_value=0.005, max_value=0.10, allow_nan=False, allow_infinity=False)

# Take-profit percentages (1% to 50%)
take_profit_pct = st.floats(min_value=0.01, max_value=0.50, allow_nan=False, allow_infinity=False)

# Cash percentage (0% to 100%)
cash_pct = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Direction
direction_st = st.sampled_from(["long", "short"])


def make_untrimmed_position_at_take_profit(
    entry_price: float,
    current_price: float,
    direction: str,
    size_pct_nav: float,
    take_profit_level: float,
) -> dict:
    """Build an untrimmed position that has hit take-profit."""
    # Compute combined_pnl_pct based on direction
    if direction == "long":
        combined_pnl_pct = (current_price - entry_price) / entry_price
    else:
        combined_pnl_pct = (entry_price - current_price) / entry_price

    return {
        "ticker": "TEST",
        "direction": direction,
        "trim_status": "untrimmed",
        "size_pct_nav": size_pct_nav,
        "entry_price": entry_price,
        "current_price": current_price,
        "combined_pnl_pct": combined_pnl_pct,
        "take_profit": f"{take_profit_level * 100}%",
        "status": "active",
    }


# ---------------------------------------------------------------------------
# Property 6: Take-profit trim halves position and sets trail stop
# ---------------------------------------------------------------------------


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    direction=direction_st,
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property6_trim_halves_size(entry_price, gain_pct, direction, size_pct_nav, cash):
    """
    Property 6 (size): For any untrimmed position with combined_pnl_pct >= take_profit,
    after execute_trim, size_pct_nav is reduced by exactly 50%.

    **Validates: Requirements 4.1, 4.2**
    """
    # Construct a position that is definitely at take-profit
    if direction == "long":
        current_price = entry_price * (1 + gain_pct)
    else:
        current_price = entry_price * (1 - gain_pct)

    # Take-profit level at or below the gain so trim triggers
    take_profit_level = gain_pct * 0.5  # Half the gain, so we're well above
    assume(take_profit_level > 0)

    pos = make_untrimmed_position_at_take_profit(
        entry_price, current_price, direction, size_pct_nav, take_profit_level
    )

    # Verify precondition: position should be eligible for trim
    assume(should_trim(pos))

    original_size = pos["size_pct_nav"]
    book = {"cash_pct": cash, "trade_journal": []}

    execute_trim(pos, book)

    # After trim: size is halved
    assert pos["size_pct_nav"] == original_size / 2, (
        f"Expected size to be halved: {original_size}/2 = {original_size/2}, "
        f"got {pos['size_pct_nav']}"
    )


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    direction=direction_st,
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property6_trim_sets_half_trimmed(entry_price, gain_pct, direction, size_pct_nav, cash):
    """
    Property 6 (status): For any untrimmed position with combined_pnl_pct >= take_profit,
    after execute_trim, trim_status is "half_trimmed".

    **Validates: Requirements 4.1, 4.4**
    """
    if direction == "long":
        current_price = entry_price * (1 + gain_pct)
    else:
        current_price = entry_price * (1 - gain_pct)

    take_profit_level = gain_pct * 0.5
    assume(take_profit_level > 0)

    pos = make_untrimmed_position_at_take_profit(
        entry_price, current_price, direction, size_pct_nav, take_profit_level
    )
    assume(should_trim(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trim(pos, book)

    assert pos["trim_status"] == "half_trimmed", (
        f"Expected trim_status='half_trimmed', got '{pos['trim_status']}'"
    )


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    direction=direction_st,
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property6_trim_sets_trail_stop_at_2_5_pct_from_peak(entry_price, gain_pct, direction, size_pct_nav, cash):
    """
    Property 6 (trail stop): For any untrimmed position with combined_pnl_pct >= take_profit,
    after execute_trim, trail_stop_level is set at 2.5% below peak (long) or 2.5% above peak (short).

    For long: trail = peak * (1 - 0.025)
    For short: trail = peak * (1 + 0.025)

    **Validates: Requirements 7.1, 7.4**
    """
    if direction == "long":
        current_price = entry_price * (1 + gain_pct)
    else:
        current_price = entry_price * (1 - gain_pct)

    take_profit_level = gain_pct * 0.5
    assume(take_profit_level > 0)

    pos = make_untrimmed_position_at_take_profit(
        entry_price, current_price, direction, size_pct_nav, take_profit_level
    )
    assume(should_trim(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trim(pos, book)

    assert pos["trail_stop_level"] is not None, "trail_stop_level should be set after trim"

    # The trail stop should be 2.5% from peak (current_price is the peak at trim time)
    peak_price = current_price  # At trim time, current IS the peak
    if direction == "long":
        expected = peak_price * (1 - 0.025)
    else:
        expected = peak_price * (1 + 0.025)

    assert abs(pos["trail_stop_level"] - expected) < 1e-6, (
        f"Trail stop mismatch for {direction}: "
        f"entry={entry_price}, peak={peak_price}, "
        f"expected trail={expected}, got={pos['trail_stop_level']}"
    )


# ---------------------------------------------------------------------------
# Property 7: Trail stop closure fully exits the remainder
# ---------------------------------------------------------------------------


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.02, max_value=0.50, allow_nan=False, allow_infinity=False),
    retrace_pct=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property7_trail_stop_closes_fully(entry_price, gain_pct, retrace_pct, size_pct_nav, cash):
    """
    Property 7 (close): For any half_trimmed position where the current price
    retraces past the trail_stop_level, after execute_trail_stop_close:
    status is "closed".

    **Validates: Requirements 4.3, 4.4**
    """
    # Simulate: position was trimmed at some gain, then price retraced
    direction = "long"

    peak_price = entry_price * (1 + gain_pct)
    trail_stop = compute_trail_stop_level(entry_price, peak_price, direction, method="2.5%")

    # Retrace past trail stop: current_price at or below trail stop
    current_price = trail_stop * (1 - (retrace_pct - 0.5) * 0.1)
    assume(current_price > 0)
    assume(current_price <= trail_stop)

    pos = {
        "ticker": "TEST",
        "direction": direction,
        "trim_status": "half_trimmed",
        "trail_stop_level": trail_stop,
        "size_pct_nav": size_pct_nav,
        "current_price": current_price,
        "combined_pnl_pct": (current_price - entry_price) / entry_price,
        "status": "active",
    }

    # Verify precondition
    assume(should_trail_stop_close(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trail_stop_close(pos, book)

    assert pos["status"] == "closed", (
        f"Expected status='closed', got '{pos.get('status')}'"
    )


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.02, max_value=0.50, allow_nan=False, allow_infinity=False),
    retrace_pct=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property7_trail_stop_sets_fully_exited(entry_price, gain_pct, retrace_pct, size_pct_nav, cash):
    """
    Property 7 (trim_status): For any half_trimmed position where price retraces
    past trail_stop_level, after execute_trail_stop_close:
    trim_status is "fully_exited".

    **Validates: Requirements 4.3, 4.4**
    """
    direction = "long"

    peak_price = entry_price * (1 + gain_pct)
    trail_stop = compute_trail_stop_level(entry_price, peak_price, direction, method="2.5%")

    current_price = trail_stop * (1 - (retrace_pct - 0.5) * 0.1)
    assume(current_price > 0)
    assume(current_price <= trail_stop)

    pos = {
        "ticker": "TEST",
        "direction": direction,
        "trim_status": "half_trimmed",
        "trail_stop_level": trail_stop,
        "size_pct_nav": size_pct_nav,
        "current_price": current_price,
        "combined_pnl_pct": (current_price - entry_price) / entry_price,
        "status": "active",
    }
    assume(should_trail_stop_close(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trail_stop_close(pos, book)

    assert pos["trim_status"] == "fully_exited", (
        f"Expected trim_status='fully_exited', got '{pos.get('trim_status')}'"
    )


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.02, max_value=0.50, allow_nan=False, allow_infinity=False),
    retrace_pct=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property7_trail_stop_exit_reason(entry_price, gain_pct, retrace_pct, size_pct_nav, cash):
    """
    Property 7 (exit_reason): For any half_trimmed position where price retraces
    past trail_stop_level, after execute_trail_stop_close:
    exit_reason is "trail_stop_auto".

    **Validates: Requirements 4.3, 4.4**
    """
    direction = "long"

    peak_price = entry_price * (1 + gain_pct)
    trail_stop = compute_trail_stop_level(entry_price, peak_price, direction, method="2.5%")

    current_price = trail_stop * (1 - (retrace_pct - 0.5) * 0.1)
    assume(current_price > 0)
    assume(current_price <= trail_stop)

    pos = {
        "ticker": "TEST",
        "direction": direction,
        "trim_status": "half_trimmed",
        "trail_stop_level": trail_stop,
        "size_pct_nav": size_pct_nav,
        "current_price": current_price,
        "combined_pnl_pct": (current_price - entry_price) / entry_price,
        "status": "active",
    }
    assume(should_trail_stop_close(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trail_stop_close(pos, book)

    assert pos["exit_reason"] == "trail_stop_auto", (
        f"Expected exit_reason='trail_stop_auto', got '{pos.get('exit_reason')}'"
    )


@given(
    entry_price=positive_price,
    gain_pct=st.floats(min_value=0.02, max_value=0.50, allow_nan=False, allow_infinity=False),
    size_pct_nav=position_size,
    cash=cash_pct,
)
@settings(max_examples=500)
def test_property7_trail_stop_short_direction(entry_price, gain_pct, size_pct_nav, cash):
    """
    Property 7 (short): For a short half_trimmed position where current_price >= trail_stop_level,
    after execute_trail_stop_close: position is fully closed with "trail_stop_auto".

    **Validates: Requirements 4.3, 4.4**
    """
    direction = "short"

    # For short: price dropping is profit. Peak is lower price.
    peak_price = entry_price * (1 - gain_pct)
    assume(peak_price > 0)
    trail_stop = compute_trail_stop_level(entry_price, peak_price, direction, method="2.5%")

    # For short: trail_stop is above peak_price. Price retracing UP past trail = loss
    # current_price >= trail_stop triggers close
    current_price = trail_stop * 1.01  # slightly above trail stop
    assume(current_price > 0)

    pos = {
        "ticker": "TEST",
        "direction": direction,
        "trim_status": "half_trimmed",
        "trail_stop_level": trail_stop,
        "size_pct_nav": size_pct_nav,
        "current_price": current_price,
        "combined_pnl_pct": (entry_price - current_price) / entry_price,
        "status": "active",
    }
    assume(should_trail_stop_close(pos))

    book = {"cash_pct": cash, "trade_journal": []}

    execute_trail_stop_close(pos, book)

    assert pos["status"] == "closed"
    assert pos["trim_status"] == "fully_exited"
    assert pos["exit_reason"] == "trail_stop_auto"
