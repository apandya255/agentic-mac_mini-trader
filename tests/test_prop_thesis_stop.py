# Feature: autonomous-trading-loop
# Property 9: Thesis-break closure requires both conditions
# Property 5: Stop-loss closure restores cash and records exit
"""
Property-based tests for thesis-break and stop-loss logic in monitor.py.

Property 9: Thesis-break "close" requires ALL of:
  thesis_status="review_overdue" AND combined_pnl_pct < 0 AND (today - overdue_since).days > 5.
  If any condition is missing, result is not "close".

Property 5: For any stop-triggered active position, after auto_close_stopped_positions:
  position status is "closed", cash_pct increased by 2×size_pct_nav,
  journal entry exists with exit_reason="stop_breach".

**Validates: Requirements 5.1, 5.2, 5.3, 8.1, 8.2, 8.3**
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from monitor import check_thesis_break, auto_close_stopped_positions, Alert


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for days held (positive integers)
days_held_strategy = st.integers(min_value=1, max_value=3650)

# Strategy for expected holding period in days
expected_days_strategy = st.integers(min_value=1, max_value=365)

# Strategy for days since overdue flag was set
days_since_overdue_strategy = st.integers(min_value=0, max_value=365)

# Strategy for combined P&L percentage
pnl_pct_strategy = st.floats(
    min_value=-0.99,
    max_value=0.99,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for size_pct_nav (reasonable position sizes)
size_pct_nav_strategy = st.floats(
    min_value=0.001,
    max_value=0.10,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for cash_pct (between 0 and 1)
cash_pct_strategy = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for current_price (positive)
current_price_strategy = st.floats(
    min_value=1.0,
    max_value=10000.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for direction
direction_strategy = st.sampled_from(["long", "short"])

# Strategy for trim_status of active positions
trim_status_strategy = st.sampled_from(["untrimmed", "half_trimmed"])


# ---------------------------------------------------------------------------
# Property 9: Thesis-break closure requires both conditions
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(
    days_held=days_held_strategy,
    expected_days=expected_days_strategy,
    days_since_overdue=days_since_overdue_strategy,
    combined_pnl_pct=pnl_pct_strategy,
)
def test_property_9_close_requires_all_three_conditions(
    days_held: int,
    expected_days: int,
    days_since_overdue: int,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.3**

    Property 9: check_thesis_break returns "close" if and only if ALL of:
      1) thesis_status == "review_overdue"
      2) combined_pnl_pct < 0
      3) (today - overdue_since).days > 5

    This test constructs positions that are already flagged as review_overdue
    and verifies that "close" requires conditions 2 AND 3 jointly.
    """
    today = date(2024, 6, 15)
    entry_date = today - timedelta(days=days_held)

    # Ensure position IS overdue (past holding period) so we test the close logic
    assume(days_held > expected_days)

    # Build position already in review_overdue state
    overdue_since = today - timedelta(days=days_since_overdue)
    pos = {
        "entry_date": entry_date.isoformat(),
        "expected_holding_period": f"{expected_days} days",
        "thesis_status": "review_overdue",
        "overdue_since": overdue_since.isoformat(),
        "combined_pnl_pct": combined_pnl_pct,
    }

    result = check_thesis_break(pos, today)

    # Expected: "close" iff combined_pnl_pct < 0 AND days_since_overdue > 5
    should_close = (combined_pnl_pct < 0) and (days_since_overdue > 5)

    if should_close:
        assert result == "close", (
            f"Expected 'close' but got '{result}': "
            f"pnl={combined_pnl_pct}, days_since_overdue={days_since_overdue}"
        )
    else:
        assert result != "close", (
            f"Expected NOT 'close' but got '{result}': "
            f"pnl={combined_pnl_pct}, days_since_overdue={days_since_overdue}"
        )


@settings(max_examples=300)
@given(
    days_held=days_held_strategy,
    expected_days=expected_days_strategy,
    combined_pnl_pct=pnl_pct_strategy,
)
def test_property_9_not_overdue_never_returns_close(
    days_held: int,
    expected_days: int,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.3**

    Property 9 (sub-property): If the position has NOT exceeded its expected
    holding period (days_held <= expected_days), the result is never "close".
    """
    assume(days_held <= expected_days)

    today = date(2024, 6, 15)
    entry_date = today - timedelta(days=days_held)

    pos = {
        "entry_date": entry_date.isoformat(),
        "expected_holding_period": f"{expected_days} days",
        "thesis_status": "active",
        "combined_pnl_pct": combined_pnl_pct,
    }

    result = check_thesis_break(pos, today)

    assert result is None, (
        f"Expected None for non-overdue position but got '{result}': "
        f"days_held={days_held}, expected_days={expected_days}"
    )


@settings(max_examples=300)
@given(
    days_held=days_held_strategy,
    expected_days=expected_days_strategy,
)
def test_property_9_overdue_not_yet_flagged_returns_flag_overdue(
    days_held: int,
    expected_days: int,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.3**

    Property 9 (sub-property): If the position has exceeded its holding period
    but thesis_status is still "active" (not yet flagged), the result is "flag_overdue".
    """
    assume(days_held > expected_days)

    today = date(2024, 6, 15)
    entry_date = today - timedelta(days=days_held)

    pos = {
        "entry_date": entry_date.isoformat(),
        "expected_holding_period": f"{expected_days} days",
        "thesis_status": "active",
        "combined_pnl_pct": -0.05,  # Negative P&L shouldn't matter here
    }

    result = check_thesis_break(pos, today)

    assert result == "flag_overdue", (
        f"Expected 'flag_overdue' but got '{result}': "
        f"days_held={days_held}, expected_days={expected_days}"
    )


@settings(max_examples=300)
@given(
    days_since_overdue=st.integers(min_value=6, max_value=365),
    combined_pnl_pct=st.floats(
        min_value=0.0,
        max_value=0.99,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_9_positive_pnl_prevents_close(
    days_since_overdue: int,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.3**

    Property 9 (sub-property): Even when overdue > 5 days, if combined_pnl_pct >= 0,
    the result SHALL NOT be "close".
    """
    assume(combined_pnl_pct >= 0)

    today = date(2024, 6, 15)
    entry_date = today - timedelta(days=100)  # clearly overdue
    overdue_since = today - timedelta(days=days_since_overdue)

    pos = {
        "entry_date": entry_date.isoformat(),
        "expected_holding_period": "30 days",
        "thesis_status": "review_overdue",
        "overdue_since": overdue_since.isoformat(),
        "combined_pnl_pct": combined_pnl_pct,
    }

    result = check_thesis_break(pos, today)

    assert result != "close", (
        f"Expected NOT 'close' with non-negative P&L={combined_pnl_pct}, "
        f"but got '{result}'"
    )


@settings(max_examples=300)
@given(
    days_since_overdue=st.integers(min_value=0, max_value=5),
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_9_insufficient_overdue_days_prevents_close(
    days_since_overdue: int,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.3**

    Property 9 (sub-property): Even with negative P&L, if overdue for <= 5 days,
    the result SHALL NOT be "close".
    """
    today = date(2024, 6, 15)
    entry_date = today - timedelta(days=100)  # clearly overdue
    overdue_since = today - timedelta(days=days_since_overdue)

    pos = {
        "entry_date": entry_date.isoformat(),
        "expected_holding_period": "30 days",
        "thesis_status": "review_overdue",
        "overdue_since": overdue_since.isoformat(),
        "combined_pnl_pct": combined_pnl_pct,
    }

    result = check_thesis_break(pos, today)

    assert result != "close", (
        f"Expected NOT 'close' with only {days_since_overdue} days overdue, "
        f"but got '{result}'"
    )


# ---------------------------------------------------------------------------
# Property 5: Stop-loss closure restores cash and records exit
# ---------------------------------------------------------------------------


@settings(max_examples=500)
@given(
    size_pct_nav=size_pct_nav_strategy,
    cash_pct=cash_pct_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
    trim_status=trim_status_strategy,
)
def test_property_5_stop_loss_sets_status_closed(
    size_pct_nav: float,
    cash_pct: float,
    current_price: float,
    direction: str,
    combined_pnl_pct: float,
    trim_status: str,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (a): After auto_close_stopped_positions, any stop-triggered
    active position SHALL have status="closed".
    """
    pos = {
        "ticker": "TEST",
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
        "cash_pct": cash_pct,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    auto_close_stopped_positions(book, alerts)

    assert pos["status"] == "closed", (
        f"Position status should be 'closed' after stop-loss but got '{pos['status']}'"
    )


@settings(max_examples=500)
@given(
    size_pct_nav=size_pct_nav_strategy,
    cash_pct=cash_pct_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
    trim_status=trim_status_strategy,
)
def test_property_5_stop_loss_restores_cash_by_2x_size(
    size_pct_nav: float,
    cash_pct: float,
    current_price: float,
    direction: str,
    combined_pnl_pct: float,
    trim_status: str,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (b): After auto_close_stopped_positions, cash_pct SHALL
    increase by exactly 2 × size_pct_nav.
    """
    pos = {
        "ticker": "TEST",
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
        "cash_pct": cash_pct,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    original_cash = cash_pct
    auto_close_stopped_positions(book, alerts)

    expected_cash = original_cash + size_pct_nav * 2
    assert abs(book["cash_pct"] - expected_cash) < 1e-10, (
        f"Cash mismatch: expected {expected_cash:.6f}, got {book['cash_pct']:.6f}. "
        f"original_cash={original_cash}, size_pct_nav={size_pct_nav}"
    )


@settings(max_examples=500)
@given(
    size_pct_nav=size_pct_nav_strategy,
    cash_pct=cash_pct_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
    trim_status=trim_status_strategy,
)
def test_property_5_stop_loss_records_journal_entry(
    size_pct_nav: float,
    cash_pct: float,
    current_price: float,
    direction: str,
    combined_pnl_pct: float,
    trim_status: str,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (c): After auto_close_stopped_positions, the trade journal
    SHALL contain an entry with exit_reason="stop_breach".
    """
    pos = {
        "ticker": "TEST",
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
        "cash_pct": cash_pct,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    auto_close_stopped_positions(book, alerts)

    # There must be exactly one journal entry
    assert len(book["trade_journal"]) == 1, (
        f"Expected 1 journal entry, got {len(book['trade_journal'])}"
    )
    entry = book["trade_journal"][0]
    assert entry["exit_reason"] == "stop_breach", (
        f"Expected exit_reason='stop_breach', got '{entry.get('exit_reason')}'"
    )
    assert entry["ticker"] == "TEST"
    assert "timestamp" in entry


@settings(max_examples=300)
@given(
    size_pct_nav=size_pct_nav_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_5_stop_loss_exit_price_is_slippage_adjusted(
    size_pct_nav: float,
    current_price: float,
    direction: str,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (d): The exit_price on the position SHALL be slippage-adjusted
    (adverse to trader): long exit < current_price, short exit > current_price.
    """
    pos = {
        "ticker": "TEST",
        "status": "active",
        "stop_triggered": True,
        "current_price": current_price,
        "combined_pnl_pct": combined_pnl_pct,
        "direction": direction,
        "size_pct_nav": size_pct_nav,
        "trim_status": "untrimmed",
    }
    book = {
        "nav": 10_000_000,
        "cash_pct": 0.5,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    auto_close_stopped_positions(book, alerts)

    exit_price = pos["exit_price"]

    if direction == "long":
        # Long exit: price × (1 - bps/10000) → less than current
        assert exit_price < current_price, (
            f"Long exit price should be < current ({current_price}), got {exit_price}"
        )
    else:
        # Short exit: price × (1 + bps/10000) → more than current
        assert exit_price > current_price, (
            f"Short exit price should be > current ({current_price}), got {exit_price}"
        )


@settings(max_examples=300)
@given(
    size_pct_nav=size_pct_nav_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
    combined_pnl_pct=st.floats(
        min_value=-0.99,
        max_value=-0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_5_stop_loss_appends_critical_alert(
    size_pct_nav: float,
    current_price: float,
    direction: str,
    combined_pnl_pct: float,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (e): After auto_close_stopped_positions, alerts SHALL contain
    a critical-level entry with the ticker.
    """
    pos = {
        "ticker": "TEST_ALERT",
        "status": "active",
        "stop_triggered": True,
        "current_price": current_price,
        "combined_pnl_pct": combined_pnl_pct,
        "direction": direction,
        "size_pct_nav": size_pct_nav,
        "trim_status": "untrimmed",
    }
    book = {
        "nav": 10_000_000,
        "cash_pct": 0.5,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    auto_close_stopped_positions(book, alerts)

    # Must have at least one critical alert for the ticker
    critical_alerts = [a for a in alerts if a.level == "critical" and a.ticker == "TEST_ALERT"]
    assert len(critical_alerts) >= 1, (
        f"Expected at least 1 critical alert for 'TEST_ALERT', got {len(critical_alerts)}. "
        f"All alerts: {[(a.level, a.ticker) for a in alerts]}"
    )


@settings(max_examples=300)
@given(
    size_pct_nav=size_pct_nav_strategy,
    current_price=current_price_strategy,
    direction=direction_strategy,
)
def test_property_5_non_triggered_positions_are_not_closed(
    size_pct_nav: float,
    current_price: float,
    direction: str,
):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 5 (inverse): Positions without stop_triggered=True SHALL NOT
    be closed by auto_close_stopped_positions.
    """
    pos = {
        "ticker": "SAFE",
        "status": "active",
        "stop_triggered": False,
        "current_price": current_price,
        "combined_pnl_pct": -0.05,
        "direction": direction,
        "size_pct_nav": size_pct_nav,
        "trim_status": "untrimmed",
    }
    book = {
        "nav": 10_000_000,
        "cash_pct": 0.5,
        "positions": [pos],
        "trade_journal": [],
    }
    alerts = []

    result = auto_close_stopped_positions(book, alerts)

    assert result == 0
    assert pos["status"] == "active", (
        f"Non-triggered position should remain active but got '{pos['status']}'"
    )
    assert book["cash_pct"] == 0.5
    assert len(book["trade_journal"]) == 0
