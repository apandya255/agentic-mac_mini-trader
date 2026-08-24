"""
Property-based test for cash accounting in Phase 8 auto-booking.

Property 4: Cash accounting is consistent through booking.
After booking: cash_pct = original_cash_pct - 2 × size_pct_nav

For any valid order that passes all gates and is not circuit-breaker-held,
after booking the position, cash_pct equals the original cash_pct minus
2 × size_pct_nav (both legs of the pair trade).

**Validates: Requirements 1.4**
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# Strategies for generating valid test inputs
# size_pct_nav between 1% and 5% of NAV (realistic position sizes)
size_pct_nav_strategy = st.floats(min_value=0.01, max_value=0.05, allow_nan=False, allow_infinity=False)

# initial cash_pct must be sufficient to cover the trade (2 × size)
# We generate cash_pct in range [0.11, 1.0] to guarantee it covers any size up to 0.05
initial_cash_pct_strategy = st.floats(min_value=0.11, max_value=1.0, allow_nan=False, allow_infinity=False)


def make_passing_order(size_pct_nav: float, proposal_id: str = "prop_001") -> dict:
    """Create an order that passes all gates (conviction ≥ 5, risk approved, execute=True)."""
    return {
        "ticker": "XOM",
        "direction": "long",
        "hedge_ticker": "XLE",
        "hedge_direction": "short",
        "conviction": 8,
        "risk_decision": {"decision": "approved", "rationale": "all clear"},
        "execute": True,
        "size_pct_nav": size_pct_nav,
        "proposal_id": proposal_id,
        "order_id": f"order_{proposal_id}",
        "stop_loss_method": "trailing 2.5% from peak",
        "take_profit": "5% triggers review",
        "expected_holding_period": "60 days",
        "pm_rationale": "Strong conviction pair trade",
        "_tech_score": {"technical_score": 7},
        "_debates": [{"stance": "support"}],
    }


def run_phase_8_with_book(orders: list[dict], initial_cash_pct: float) -> dict:
    """Run phase_8_update_book with a controlled book state and return the updated book."""
    import run_cycle

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Set up temporary state
        state_dir = tmp_path / "memos" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        orders_dir = tmp_path / "memos" / "orders"
        orders_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = tmp_path / "memos" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        proposals_dir = tmp_path / "memos" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        # Create initial book with the given cash_pct and matching NAV
        # session_open_nav == nav ensures circuit breaker is NOT active (drawdown = 0)
        nav = 10_000_000
        book = {
            "nav": nav,
            "initial_nav": nav,
            "cash_pct": initial_cash_pct,
            "session_open_nav": nav,  # Same as nav → circuit breaker inactive
            "positions": [],
            "trade_journal": [],
        }
        book_path = state_dir / "book.json"
        book_path.write_text(json.dumps(book, indent=2))

        # Mock price service to return known prices
        mock_price_service = MagicMock()
        mock_price_service.get_latest_close.side_effect = lambda t: {
            "XOM": 105.50,
            "XLE": 88.20,
        }.get(t, 100.0)

        mock_price_service_class = MagicMock(return_value=mock_price_service)

        with patch.object(run_cycle, "STATE_FILE", book_path), \
             patch.object(run_cycle, "MEMOS_DIR", tmp_path / "memos"), \
             patch.object(run_cycle, "LOG_DIR", tmp_path / "memos" / "logs"), \
             patch("data_platform.prices.PriceService", mock_price_service_class):
            run_cycle.phase_8_update_book(orders)

        return json.loads(book_path.read_text())


@given(
    size_pct_nav=size_pct_nav_strategy,
    initial_cash_pct=initial_cash_pct_strategy,
)
@settings(max_examples=200)
def test_property4_cash_accounting_single_order(size_pct_nav, initial_cash_pct):
    """
    Property 4: For a single order that passes all gates with circuit breaker
    inactive, after booking: cash_pct = original_cash_pct - 2 × size_pct_nav.

    **Validates: Requirements 1.4**
    """
    # Ensure cash is sufficient for the trade
    assume(initial_cash_pct >= 2 * size_pct_nav)

    order = make_passing_order(size_pct_nav=size_pct_nav)
    book = run_phase_8_with_book([order], initial_cash_pct)

    # The position must have been booked (gates pass, no circuit breaker)
    assert len(book["positions"]) == 1, "Order should have been booked"

    expected_cash = initial_cash_pct - (2 * size_pct_nav)
    assert book["cash_pct"] == expected_cash, (
        f"Cash accounting mismatch: "
        f"got {book['cash_pct']}, expected {expected_cash} "
        f"(original={initial_cash_pct}, size={size_pct_nav}, deducted={2*size_pct_nav})"
    )


@given(
    size1=size_pct_nav_strategy,
    size2=size_pct_nav_strategy,
    initial_cash_pct=st.floats(min_value=0.21, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property4_cash_accounting_multiple_orders(size1, size2, initial_cash_pct):
    """
    Property 4 (extended): For multiple orders, each deduction is independent.
    After booking N orders: cash_pct = original - sum(2 × size_pct_nav_i).

    **Validates: Requirements 1.4**
    """
    # Ensure cash is sufficient for both trades
    total_deduction = 2 * size1 + 2 * size2
    assume(initial_cash_pct >= total_deduction)

    orders = [
        make_passing_order(size_pct_nav=size1, proposal_id="p1"),
        make_passing_order(size_pct_nav=size2, proposal_id="p2"),
    ]
    # Make second order use a different ticker to avoid price service issues
    orders[1]["ticker"] = "XLE"
    orders[1]["hedge_ticker"] = "XOM"
    orders[1]["direction"] = "short"
    orders[1]["hedge_direction"] = "long"

    book = run_phase_8_with_book(orders, initial_cash_pct)

    # Both positions should be booked
    assert len(book["positions"]) == 2, "Both orders should have been booked"

    expected_cash = initial_cash_pct - total_deduction
    assert abs(book["cash_pct"] - expected_cash) < 1e-10, (
        f"Cash accounting mismatch for multiple orders: "
        f"got {book['cash_pct']}, expected {expected_cash} "
        f"(original={initial_cash_pct}, sizes=[{size1}, {size2}], "
        f"total_deducted={total_deduction})"
    )
