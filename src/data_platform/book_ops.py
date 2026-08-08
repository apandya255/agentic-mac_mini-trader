"""
Book Operations Module for the Agentic AI Trading System.

Shared lock-aware read/write of book.json and mark-to-market computation.
Used by price_poller, mark_to_market.py, and serve.py.

Key design:
- Lock file is separate (book.json.lock) so reads don't block.
- Write uses atomic rename (write .tmp then os.replace) to prevent partial reads.
- Trail breach threshold: 2.5% fall from Peak (combined P&L).
- Target touch threshold: +5% combined P&L.
- P&L: (current - entry) / entry for longs, (entry - current) / entry for shorts.
- Peak tracking: best level in position's favor since entry.

Usage:
    from src.data_platform.book_ops import book_lock, load_book, save_book, mark_positions

    with book_lock(timeout=30):
        book = load_book()
        book = mark_positions(book, price_service)
        save_book(book)
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .prices import PriceService

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BOOK_PATH = Path(__file__).parent.parent.parent / "memos" / "state" / "book.json"
LOCK_PATH = BOOK_PATH.with_suffix(".json.lock")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LockTimeout(Exception):
    """Raised when the book lock cannot be acquired within the timeout."""
    pass


# ---------------------------------------------------------------------------
# Lock Context Manager
# ---------------------------------------------------------------------------

@contextmanager
def book_lock(timeout: int = 30):
    """
    Acquire an exclusive advisory lock on book.json.lock.

    Uses fcntl.flock with non-blocking attempts and polling retry.
    The lock is held only during the context block (read-modify-write cycle).

    Args:
        timeout: Maximum seconds to wait for the lock (default 30).

    Yields:
        The lock file descriptor.

    Raises:
        LockTimeout: If the lock cannot be acquired within the timeout.
    """
    # Ensure the lock file's parent directory exists
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    lock_fd = open(LOCK_PATH, "w")
    deadline = time.time() + timeout

    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield lock_fd
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            return
        except (BlockingIOError, OSError):
            if time.time() >= deadline:
                lock_fd.close()
                raise LockTimeout(
                    f"Could not acquire book lock within {timeout}s"
                )
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_book() -> dict:
    """
    Read book.json and return it as a dict.

    Caller should hold the lock if performing a write cycle (read-modify-write).
    For read-only dashboard use, no lock is needed (atomic writes guarantee
    consistent reads — worst case shows data from the previous write).

    Returns:
        The book state as a dict. Returns an empty default if file doesn't exist.
    """
    if not BOOK_PATH.exists():
        return {
            "nav": 0,
            "initial_nav": 0,
            "cash_pct": 1.0,
            "positions": [],
            "trade_journal": [],
            "last_marked": None,
        }

    with open(BOOK_PATH, "r") as f:
        return json.load(f)


def save_book(book: dict) -> None:
    """
    Atomic write of book.json: write to .tmp then os.replace.

    This prevents partial reads by concurrent readers — the file either
    has the old content or the new content, never half-written data.

    Args:
        book: The book state dict to persist.
    """
    BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = BOOK_PATH.with_suffix(".json.tmp")

    with open(tmp_path, "w") as f:
        json.dump(book, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, BOOK_PATH)


# ---------------------------------------------------------------------------
# Mark Positions to Market
# ---------------------------------------------------------------------------

def mark_positions(book: dict, price_service: "PriceService") -> dict:
    """
    Recompute P&L for all active positions using latest prices.

    For each active position:
    - Fetches the latest close price for the primary and hedge tickers.
    - Computes unrealized P&L for each leg:
        - Long: (current - entry) / entry
        - Short: (entry - current) / entry
    - Combined P&L = average of both legs' P&L.
    - Updates the Peak field if position has reached a new best combined P&L.
    - Reads carry adjustment from the position (if present) and adds to combined P&L.

    Args:
        book: The book state dict (will be mutated and returned).
        price_service: A PriceService instance for fetching latest prices.

    Returns:
        The updated book dict with refreshed P&L and peak values.
    """
    positions = book.get("positions", [])

    for pos in positions:
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker")
        hedge_ticker = pos.get("hedge_ticker")
        direction = pos.get("direction", "long")
        hedge_direction = pos.get("hedge_direction", "short")

        # Fetch latest prices
        ticker_price = price_service.get_latest_close(ticker)
        hedge_price = price_service.get_latest_close(hedge_ticker)

        if ticker_price is None or hedge_price is None:
            continue  # Skip if we can't get prices

        # Update current prices
        pos["current_price"] = ticker_price
        pos["hedge_current_price"] = hedge_price

        # Compute P&L for primary leg
        entry_price = pos.get("entry_price", 0)
        hedge_entry_price = pos.get("hedge_entry_price", 0)

        if entry_price <= 0 or hedge_entry_price <= 0:
            continue

        # Primary leg P&L
        if direction == "long":
            unrealized_pnl = (ticker_price - entry_price) / entry_price
        else:
            unrealized_pnl = (entry_price - ticker_price) / entry_price

        # Hedge leg P&L
        if hedge_direction == "short":
            hedge_pnl = (hedge_entry_price - hedge_price) / hedge_entry_price
        else:
            hedge_pnl = (hedge_price - hedge_entry_price) / hedge_entry_price

        pos["unrealized_pnl_pct"] = unrealized_pnl
        pos["hedge_unrealized_pnl_pct"] = hedge_pnl

        # Combined P&L = average of both legs
        combined_pnl = (unrealized_pnl + hedge_pnl) / 2.0

        # Add carry adjustment if present (accrued carry in %)
        carry_adj = pos.get("carry_adjustment_pct", 0.0)
        combined_pnl += carry_adj

        pos["combined_pnl_pct"] = combined_pnl

        # Update peak tracking
        pos = update_peak(pos, combined_pnl)

    # Update the last_marked timestamp
    book["last_marked"] = datetime.now().isoformat()

    return book


# ---------------------------------------------------------------------------
# Peak Tracking
# ---------------------------------------------------------------------------

def update_peak(position: dict, current_pnl: float) -> dict:
    """
    Track the best combined P&L level in the position's favor since entry.

    Peak only ratchets up (for any direction), never down. This is the anchor
    for the trailing stop calculation.

    Args:
        position: The position dict (will be mutated and returned).
        current_pnl: The current combined P&L percentage (as a decimal, e.g. 0.05 = 5%).

    Returns:
        The updated position dict with refreshed peak_pnl field.
    """
    current_peak = position.get("peak_pnl", 0.0)

    # Peak only moves up — best P&L achieved
    if current_pnl > current_peak:
        position["peak_pnl"] = current_pnl

    return position


# ---------------------------------------------------------------------------
# Trail Breach Detection
# ---------------------------------------------------------------------------

# Threshold: 2.5% fall from Peak combined P&L
TRAIL_BREACH_THRESHOLD = 0.025


def check_trail_breach(position: dict) -> bool:
    """
    Detect if a position has breached its trailing stop.

    A trail breach occurs when the combined P&L has fallen 2.5 percentage points
    from the Peak P&L. This means:
        peak_pnl - combined_pnl_pct >= 0.025

    Example:
        Peak = +3% → breach if combined P&L drops to +0.5% or below.
        Peak = 0% → breach if combined P&L drops to -2.5% or below.

    Args:
        position: The position dict containing peak_pnl and combined_pnl_pct.

    Returns:
        True if the trail has been breached, False otherwise.
    """
    if position.get("status") != "active":
        return False

    peak_pnl = position.get("peak_pnl", 0.0)
    combined_pnl = position.get("combined_pnl_pct", 0.0)

    drawdown_from_peak = peak_pnl - combined_pnl

    return drawdown_from_peak >= TRAIL_BREACH_THRESHOLD


# ---------------------------------------------------------------------------
# Target Touch Detection
# ---------------------------------------------------------------------------

# Threshold: +5% combined P&L triggers PM review
TARGET_TOUCH_THRESHOLD = 0.05


def check_target_touch(position: dict) -> bool:
    """
    Detect if a position has reached the +5% target (PM review trigger).

    When target is touched, the position should be surfaced for PM review.
    The system does NOT auto-exit — the PM decides to take profit or extend.

    Args:
        position: The position dict containing combined_pnl_pct.

    Returns:
        True if the combined P&L has reached +5%, False otherwise.
    """
    if position.get("status") != "active":
        return False

    combined_pnl = position.get("combined_pnl_pct", 0.0)

    return combined_pnl >= TARGET_TOUCH_THRESHOLD
