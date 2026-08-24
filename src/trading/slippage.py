"""
Slippage model for paper-trade fill pricing.

Computes slippage-adjusted fill prices that are always adverse to the trader,
simulating realistic execution costs in paper trading.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

import os


def get_slippage_bps() -> int:
    """
    Read slippage from the SLIPPAGE_BPS environment variable.

    Returns the configured slippage in basis points, defaulting to 5 if
    the variable is not set or contains an invalid value.
    """
    raw = os.environ.get("SLIPPAGE_BPS", "5")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 5


def compute_fill_price(
    last_observed_price: float,
    direction: str,
    side: str,
    slippage_bps: int | None = None,
) -> float:
    """
    Compute slippage-adjusted fill price.

    Slippage is always adverse to the trade direction:
      - Long entry:  price × (1 + bps/10000)  — pay more
      - Short entry: price × (1 - bps/10000)  — sell for less
      - Long exit:   price × (1 - bps/10000)  — receive less
      - Short exit:  price × (1 + bps/10000)  — buy back for more

    Args:
        last_observed_price: Last observed market close price.
        direction: "long" or "short" — the position direction.
        side: "entry" or "exit" — whether entering or exiting.
        slippage_bps: Override slippage in basis points. If None, reads from env.

    Returns:
        Adjusted fill price (always adverse to the trader).

    Raises:
        ValueError: If direction/side combination is invalid.
    """
    if slippage_bps is None:
        slippage_bps = get_slippage_bps()

    factor = slippage_bps / 10_000

    if direction == "long" and side == "entry":
        return last_observed_price * (1 + factor)
    elif direction == "short" and side == "entry":
        return last_observed_price * (1 - factor)
    elif direction == "long" and side == "exit":
        return last_observed_price * (1 - factor)
    elif direction == "short" and side == "exit":
        return last_observed_price * (1 + factor)
    else:
        raise ValueError(f"Invalid direction/side combination: {direction}/{side}")
