#!/usr/bin/env python3
"""
Mark-to-Market Script

Fetches current prices for all active positions, updates unrealized P&L,
recomputes NAV, and appends a snapshot to P&L history for equity curve charting.

Run daily (or intraday) to keep the book current:
    python3 mark_to_market.py
"""

import warnings
warnings.filterwarnings('ignore')

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService

# Paths
BASE_DIR = Path(__file__).parent
BOOK_PATH = BASE_DIR / "memos" / "state" / "book.json"
HISTORY_PATH = BASE_DIR / "memos" / "state" / "pnl_history.json"

price_service = PriceService()
logger = logging.getLogger(__name__)


def main():
    if not BOOK_PATH.exists():
        print("No book.json found — nothing to mark.")
        return

    book = json.loads(BOOK_PATH.read_text())
    active_positions = [p for p in book.get("positions", []) if p.get("status") == "active"]

    if not active_positions:
        print("No active positions — nothing to mark.")
        record_snapshot(book)
        return

    # Backfill: ensure complete price history for each active position
    for pos in active_positions:
        ticker = pos.get("ticker")
        entry_date_str = pos.get("entry_date")
        if not ticker or not entry_date_str:
            continue
        try:
            entry_dt = date.fromisoformat(entry_date_str)
            result = price_service.backfill_position(ticker, entry_dt)
            if result["days_backfilled"] > 0:
                logger.info("Backfill: %s filled %d days, %d gaps remaining",
                           ticker, result["days_backfilled"], result["gaps_remaining"])
        except Exception as e:
            logger.warning("Backfill failed for %s: %s", ticker, e)

    print(f"Marking {len(active_positions)} active position(s) to market...\n")

    total_pnl_dollars = 0
    initial_nav = book.get("initial_nav", 10_000_000)

    for pos in active_positions:
        ticker = pos.get("ticker", "")
        hedge_ticker = pos.get("hedge_ticker", "")
        direction = pos.get("direction", "long")
        hedge_dir = pos.get("hedge_direction", "short")

        # Fetch current prices
        current = price_service.get_latest_close(ticker)
        hedge_current = price_service.get_latest_close(hedge_ticker) if hedge_ticker else None

        if current is not None:
            pos["current_price"] = current
        if hedge_current is not None:
            pos["hedge_current_price"] = hedge_current

        # Main leg P&L
        entry = pos.get("entry_price")
        if entry and current:
            if direction == "long":
                pnl = (current - entry) / entry
            else:
                pnl = (entry - current) / entry
            pos["unrealized_pnl_pct"] = pnl
        else:
            pnl = None
            pos["unrealized_pnl_pct"] = None

        # Hedge leg P&L
        hedge_entry = pos.get("hedge_entry_price")
        if hedge_entry and hedge_current:
            if hedge_dir == "short":
                hedge_pnl = (hedge_entry - hedge_current) / hedge_entry
            else:
                hedge_pnl = (hedge_current - hedge_entry) / hedge_entry
            pos["hedge_unrealized_pnl_pct"] = hedge_pnl
        else:
            hedge_pnl = None
            pos["hedge_unrealized_pnl_pct"] = None

        # Combined
        if pnl is not None and hedge_pnl is not None:
            combined = (pnl + hedge_pnl) / 2
        elif pnl is not None:
            combined = pnl
        else:
            combined = None
        pos["combined_pnl_pct"] = combined

        # ── Per-position daily price history ──
        today = datetime.now().strftime("%Y-%m-%d")
        if "price_history" not in pos:
            pos["price_history"] = []

        # Compute daily change vs previous close
        prev_close = None
        if pos["price_history"]:
            prev_close = pos["price_history"][-1].get("price")

        if current is not None and prev_close is not None and prev_close != 0:
            daily_chg = (current - prev_close) / prev_close
        else:
            daily_chg = 0.0

        daily_record = {
            "date": today,
            "price": current,
            "hedge_price": hedge_current,
            "combined_pnl_pct": combined,
            "daily_change_pct": daily_chg,
        }

        # One record per day (overwrite if same day)
        if pos["price_history"] and pos["price_history"][-1].get("date") == today:
            pos["price_history"][-1] = daily_record
        else:
            pos["price_history"].append(daily_record)

        # Keep last 90 days max
        pos["price_history"] = pos["price_history"][-90:]

        # Store daily change on the position for quick access
        pos["daily_change_pct"] = daily_chg

        # Accumulate NAV impact
        size = pos.get("size_pct_nav", 0)
        if combined is not None:
            total_pnl_dollars += combined * size * initial_nav

        # Print
        daily_str = f"  day={daily_chg*100:+.2f}%" if daily_chg else ""
        pnl_str = f"{combined*100:+.2f}%" if combined is not None else "N/A"
        print(f"  {ticker}/{hedge_ticker}  {direction}  entry=${entry:.2f}  now=${current:.2f}  P&L={pnl_str}{daily_str}")

    # Update NAV
    book["nav"] = initial_nav + total_pnl_dollars
    book["last_marked"] = datetime.now().isoformat()

    # Check stops
    check_stop_losses(book)

    # Save
    BOOK_PATH.write_text(json.dumps(book, indent=2))

    # Record history
    record_snapshot(book)

    # Summary
    total_pnl_pct = (book["nav"] - initial_nav) / initial_nav
    print(f"\n  NAV: ${book['nav']:,.0f} ({total_pnl_pct*100:+.2f}%)")
    print(f"  Cash: {book['cash_pct']*100:.1f}%")
    print(f"  Marked at: {book['last_marked']}")


def check_stop_losses(book: dict) -> None:
    """Check if any positions have hit their trailing stop."""
    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        combined_pnl = pos.get("combined_pnl_pct")
        if combined_pnl is None:
            continue

        # Simple trailing stop check: if P&L < -2.5%, flag it
        stop_method = pos.get("stop_loss_method", "")
        if "2.5%" in stop_method and combined_pnl < -0.025:
            pos["stop_triggered"] = True
            print(f"  ⚠ STOP TRIGGERED: {pos['ticker']} at {combined_pnl*100:+.2f}%")


def record_snapshot(book: dict) -> None:
    """Append a NAV snapshot to history."""
    history = []
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text())

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "nav": book.get("nav", 10_000_000),
        "positions": len([p for p in book.get("positions", []) if p.get("status") == "active"]),
        "cash_pct": book.get("cash_pct", 1.0),
        "total_pnl_pct": (book.get("nav", 10_000_000) - book.get("initial_nav", 10_000_000)) / book.get("initial_nav", 10_000_000),
    }

    # One snapshot per day (overwrite same day)
    if history and history[-1].get("date") == snapshot["date"]:
        history[-1] = snapshot
    else:
        history.append(snapshot)

    HISTORY_PATH.write_text(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
