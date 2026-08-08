#!/usr/bin/env python3
"""
Sync desk/positions.md from memos/state/book.json.
Run after mark_to_market.py to keep the human-readable book current.
"""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
BOOK_PATH = BASE_DIR / "memos" / "state" / "book.json"
POSITIONS_PATH = BASE_DIR / "desk" / "positions.md"


def main():
    if not BOOK_PATH.exists():
        print("No book.json found.")
        return

    book = json.loads(BOOK_PATH.read_text())
    positions = [p for p in book.get("positions", []) if p.get("status") == "active"]
    nav = book.get("nav", 10_000_000)
    initial_nav = book.get("initial_nav", 10_000_000)
    cash_pct = book.get("cash_pct", 1.0)

    # Compute gross exposure
    gross = sum(abs(p.get("size_pct_nav", 0)) * 2 for p in positions)  # *2 for hedge

    lines = []
    lines.append("# The Book — desk/positions.md\n")
    lines.append("Source of truth. Managed autonomously by the PM seat per AGENTS.md; the principal is informed, never asked. Status: PAPER, permanently.\n")
    lines.append("")
    lines.append("| # | Opened | Instrument | Dir | Wts | Entry | Last | Peak | Trail % | Target | P&L % | Size %NAV | Loss-at-trail (bps) | Tier | Status |")
    lines.append("|---|--------|------------|-----|-----|-------|------|------|---------|--------|-------|-----------|--------------------|------|--------|")

    for i, p in enumerate(positions, 1):
        ticker = p.get("ticker", "?")
        hedge = p.get("hedge_ticker", "?")
        direction = p.get("direction", "long")
        entry_price = p.get("entry_price", 0)
        hedge_entry = p.get("hedge_entry_price", 1)
        current_price = p.get("current_price", entry_price)
        hedge_current = p.get("hedge_current_price", hedge_entry)
        entry_date = p.get("entry_date", "?")
        size = p.get("size_pct_nav", 0)
        combined_pnl = p.get("combined_pnl_pct", 0)
        status = p.get("status", "active").upper()

        # Pair ratio
        entry_ratio = entry_price / hedge_entry if hedge_entry else 0
        last_ratio = current_price / hedge_current if hedge_current else 0

        # Peak = max of last ratio (simplified — real tracking would store this)
        peak_ratio = max(entry_ratio, last_ratio)

        # Loss at trail in bps NAV
        trail_pct = 2.5
        loss_at_trail = trail_pct / 100 * size * 100 * 100  # bps

        pnl_str = f"{combined_pnl*100:+.2f}%" if combined_pnl else "0.00%"

        lines.append(f"| {i} | {entry_date} | {ticker}/{hedge} | {direction.capitalize()} | 1:1 | {entry_ratio:.4f} | {last_ratio:.4f} | {peak_ratio:.4f} | {trail_pct}% | +5% | {pnl_str} | {size*100:.1f}% | {loss_at_trail:.0f} | standard | {status} |")

    deployed = (1 - cash_pct) * 100
    lines.append("")
    lines.append(f"NAV: ${nav:,.0f} (paper). Deployed: {deployed:.0f}%. Cash: {cash_pct*100:.0f}%. Book stance: long-biased, {gross:.2f}x gross leverage. Conviction slots used: 0 of 2. Last factor check: pending.")
    lines.append(f"\n_Last synced: {datetime.now().isoformat()}_")

    POSITIONS_PATH.write_text("\n".join(lines))
    print(f"desk/positions.md synced — {len(positions)} active positions.")


if __name__ == "__main__":
    main()
