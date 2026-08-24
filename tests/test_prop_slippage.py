"""
Property-based tests for src/trading/slippage.py

Property 1: Slippage is always adverse to the trader.
For any valid direction/side, slippage-adjusted price is strictly worse
than the unadjusted price.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from src.trading.slippage import compute_fill_price


# Strategy: positive prices (realistic market prices)
positive_price = st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

# Strategy: slippage > 0 to guarantee strict inequality
positive_slippage_bps = st.integers(min_value=1, max_value=500)


@given(price=positive_price, slippage_bps=positive_slippage_bps)
@settings(max_examples=500)
def test_property1_long_entry_adverse(price, slippage_bps):
    """
    Property 1 (long entry): For a long entry, the trader pays MORE than
    the unadjusted price. fill_price > last_observed_price.

    **Validates: Requirements 9.1, 9.2**
    """
    fill = compute_fill_price(price, "long", "entry", slippage_bps=slippage_bps)
    assert fill > price, (
        f"Long entry should cost MORE than observed price: "
        f"fill={fill}, price={price}, bps={slippage_bps}"
    )


@given(price=positive_price, slippage_bps=positive_slippage_bps)
@settings(max_examples=500)
def test_property1_short_entry_adverse(price, slippage_bps):
    """
    Property 1 (short entry): For a short entry, the trader receives LESS
    than the unadjusted price. fill_price < last_observed_price.

    **Validates: Requirements 9.1, 9.3**
    """
    fill = compute_fill_price(price, "short", "entry", slippage_bps=slippage_bps)
    assert fill < price, (
        f"Short entry should receive LESS than observed price: "
        f"fill={fill}, price={price}, bps={slippage_bps}"
    )


@given(price=positive_price, slippage_bps=positive_slippage_bps)
@settings(max_examples=500)
def test_property1_long_exit_adverse(price, slippage_bps):
    """
    Property 1 (long exit): For a long exit, the trader receives LESS
    than the unadjusted price. fill_price < last_observed_price.

    **Validates: Requirements 9.1, 9.4**
    """
    fill = compute_fill_price(price, "long", "exit", slippage_bps=slippage_bps)
    assert fill < price, (
        f"Long exit should receive LESS than observed price: "
        f"fill={fill}, price={price}, bps={slippage_bps}"
    )


@given(price=positive_price, slippage_bps=positive_slippage_bps)
@settings(max_examples=500)
def test_property1_short_exit_adverse(price, slippage_bps):
    """
    Property 1 (short exit): For a short exit, the trader pays MORE
    than the unadjusted price. fill_price > last_observed_price.

    **Validates: Requirements 9.1, 9.5**
    """
    fill = compute_fill_price(price, "short", "exit", slippage_bps=slippage_bps)
    assert fill > price, (
        f"Short exit should cost MORE than observed price: "
        f"fill={fill}, price={price}, bps={slippage_bps}"
    )


@given(
    price=positive_price,
    slippage_bps=positive_slippage_bps,
    direction=st.sampled_from(["long", "short"]),
    side=st.sampled_from(["entry", "exit"]),
)
@settings(max_examples=500)
def test_property1_slippage_always_adverse_combined(price, slippage_bps, direction, side):
    """
    Property 1 (combined): For ANY valid direction/side combination with
    positive slippage, the fill price is strictly worse for the trader
    than the unadjusted price.

    Adverse means:
      - Entries cost more (long) or sell for less (short)
      - Exits receive less (long) or buy back for more (short)

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
    """
    fill = compute_fill_price(price, direction, side, slippage_bps=slippage_bps)

    if direction == "long" and side == "entry":
        # Long entry: trader pays more → fill > price
        assert fill > price
    elif direction == "short" and side == "entry":
        # Short entry: trader sells for less → fill < price
        assert fill < price
    elif direction == "long" and side == "exit":
        # Long exit: trader receives less → fill < price
        assert fill < price
    elif direction == "short" and side == "exit":
        # Short exit: trader buys back for more → fill > price
        assert fill > price
