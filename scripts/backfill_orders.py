"""
Backfill Orders Script
======================
Books the 5 pending orders from Aug 8, 2026 into book.json with entry prices
from Aug 11, 2026 (Monday after the Saturday generation date).

Fetches/updates price data, computes P&L, builds price history, and updates NAV.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, date, timedelta

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data_platform.prices import PriceService

STATE_FILE = PROJECT_ROOT / "memos" / "state" / "book.json"
HISTORY_FILE = PROJECT_ROOT / "memos" / "state" / "pnl_history.json"

# Initialize price service and update data for all tickers
price_service = PriceService()

TICKERS = ["VLO", "RSPG", "ORCL", "RSPT", "EWJ", "EFA", "XLE", "RSP", "EWG"]

print("Updating price data for all tickers...")
inserted = price_service.update(TICKERS, lookback_days=400, progress=True)
print(f"  {inserted} rows inserted/updated\n")

# Entry date: Monday Aug 11, 2026 (first trading day after Aug 8 Saturday)
ENTRY_DATE = "2026-08-11"


def get_price_on_or_before(ticker, target_date):
    """Get close price on target_date or the most recent available before it."""
    import sqlite3
    db_path = price_service.db_path
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT close, date FROM price_history WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (ticker, target_date)
        ).fetchone()
    if row:
        return row[0], row[1]
    # Fallback: get the latest available price regardless of date
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT close, date FROM price_history WHERE ticker = ? AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
            (ticker,)
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def get_latest_price(ticker):
    """Get the most recent price available."""
    return price_service.get_latest_close(ticker)


# Define orders
orders = [
    {
        "ticker": "VLO", "direction": "short",
        "hedge_ticker": "RSPG", "hedge_direction": "long",
        "size_pct_nav": 0.03, "conviction": 7,
        "proposal_id": "fund_energy_20260808_vlo_short",
        "stop_loss_method": "trailing 2.5% on VLO/RSPG pair ratio",
        "take_profit": "ratio 2.45 target",
        "expected_holding_period": "2-6 weeks",
        "review_date": "2026-08-12",
    },
    {
        "ticker": "ORCL", "direction": "long",
        "hedge_ticker": "RSPT", "hedge_direction": "short",
        "size_pct_nav": 0.02, "conviction": 6,
        "proposal_id": "fund_infotech_20260808_orcl",
        "stop_loss_method": "pair-ratio trailing stop, initial 1.92",
        "take_profit": "+5% combined P&L",
        "expected_holding_period": "4-8 weeks",
        "review_date": "2026-08-15",
    },
    {
        "ticker": "EWJ", "direction": "long",
        "hedge_ticker": "EFA", "hedge_direction": "short",
        "size_pct_nav": 0.02, "conviction": 6,
        "proposal_id": "macro_asia_japan_2026-08-08T21:45",
        "stop_loss_method": "hard stop at EWJ/EFA ratio 0.874",
        "take_profit": "0.925 ratio target",
        "expected_holding_period": "4-10 weeks",
        "review_date": "2026-08-14",
    },
    {
        "ticker": "XLE", "direction": "long",
        "hedge_ticker": "RSP", "hedge_direction": "short",
        "size_pct_nav": 0.02, "conviction": 6,
        "proposal_id": "macro_commodities_2026-08-08T21:50",
        "stop_loss_method": "trailing 2.5%, floor at 55.68",
        "take_profit": "+5% triggers PM review",
        "expected_holding_period": "4-8 weeks",
        "review_date": "2026-08-10",
    },
    {
        "ticker": "EWG", "direction": "long",
        "hedge_ticker": "EFA", "hedge_direction": "short",
        "size_pct_nav": 0.03, "conviction": 7,
        "proposal_id": "macro_westerneurope_20260808t2156",
        "stop_loss_method": "2.5% trailing from ratio peak",
        "take_profit": "5% ratio target",
        "expected_holding_period": "1-3 months",
        "review_date": "2026-08-21",
    },
]

# Load existing book
book = json.loads(STATE_FILE.read_text())
initial_nav = book["initial_nav"]

print(f"NAV: ${initial_nav:,.0f}")
print(f"Target entry date: {ENTRY_DATE}")
print("\n" + "=" * 70)
print("FETCHING ENTRY PRICES & BUILDING POSITIONS")
print("=" * 70)

positions = []
total_allocated = 0

for order in orders:
    ticker = order["ticker"]
    hedge_ticker = order["hedge_ticker"]

    entry_price, entry_date_actual = get_price_on_or_before(ticker, ENTRY_DATE)
    hedge_entry_price, hedge_entry_date_actual = get_price_on_or_before(hedge_ticker, ENTRY_DATE)
    current_price = get_latest_price(ticker)
    hedge_current_price = get_latest_price(hedge_ticker)

    if entry_price is None:
        print(f"\n  ⚠️  WARNING: No price data at all for {ticker} — SKIPPING")
        continue
    if hedge_entry_price is None:
        print(f"\n  ⚠️  WARNING: No price data at all for {hedge_ticker} — SKIPPING")
        continue
    if current_price is None:
        print(f"\n  ⚠️  WARNING: No current price for {ticker} — SKIPPING")
        continue
    if hedge_current_price is None:
        print(f"\n  ⚠️  WARNING: No current price for {hedge_ticker} — SKIPPING")
        continue

    # Use the actual date we found the entry price at
    effective_entry_date = entry_date_actual if entry_date_actual else ENTRY_DATE

    # Note if entry date differs from target
    date_note = ""
    if entry_date_actual and entry_date_actual != ENTRY_DATE:
        date_note = f" (actual: {entry_date_actual})"

    print(f"\n{'─' * 70}")
    print(f"  {ticker} {order['direction'].upper()} @ ${entry_price:.2f}{date_note} → ${current_price:.2f}")
    print(f"  {hedge_ticker} {order['hedge_direction'].upper()} @ ${hedge_entry_price:.2f} → ${hedge_current_price:.2f}")

    # Compute P&L
    if order["direction"] == "long":
        main_pnl = (current_price - entry_price) / entry_price
    else:
        main_pnl = (entry_price - current_price) / entry_price

    if order["hedge_direction"] == "short":
        hedge_pnl = (hedge_entry_price - hedge_current_price) / hedge_entry_price
    else:
        hedge_pnl = (hedge_current_price - hedge_entry_price) / hedge_entry_price

    combined_pnl = (main_pnl + hedge_pnl) / 2

    print(f"  Main P&L: {main_pnl*100:+.2f}% | Hedge P&L: {hedge_pnl*100:+.2f}% | Combined: {combined_pnl*100:+.2f}%")

    # Build price history from entry date to today
    history_df = price_service.get_history(ticker, lookback_days=90)
    hedge_history_df = price_service.get_history(hedge_ticker, lookback_days=90)

    price_history = []
    if not history_df.empty:
        # Filter to dates >= effective entry date
        entry_dt = datetime.strptime(effective_entry_date, "%Y-%m-%d")
        filtered = history_df[history_df.index >= entry_dt]

        for dt, row in filtered.iterrows():
            date_str = dt.strftime("%Y-%m-%d")
            price = row["close"]
            # Find matching hedge price
            hedge_price = None
            if not hedge_history_df.empty and dt in hedge_history_df.index:
                hedge_price = hedge_history_df.loc[dt, "close"]

            # Daily change
            prev_price = price_history[-1]["price"] if price_history else entry_price
            daily_chg = (price - prev_price) / prev_price if prev_price else 0

            # Combined P&L at this point
            if order["direction"] == "long":
                mp = (price - entry_price) / entry_price
            else:
                mp = (entry_price - price) / entry_price

            if hedge_price and order["hedge_direction"] == "short":
                hp = (hedge_entry_price - hedge_price) / hedge_entry_price
            elif hedge_price:
                hp = (hedge_price - hedge_entry_price) / hedge_entry_price
            else:
                hp = 0

            cpnl = (mp + hp) / 2

            price_history.append({
                "date": date_str,
                "price": price,
                "hedge_price": hedge_price,
                "combined_pnl_pct": round(cpnl, 6),
                "daily_change_pct": round(daily_chg, 6),
            })

    print(f"  Price history: {len(price_history)} days")

    position = {
        "ticker": ticker,
        "direction": order["direction"],
        "hedge_ticker": hedge_ticker,
        "hedge_direction": order["hedge_direction"],
        "size_pct_nav": order["size_pct_nav"],
        "conviction": order["conviction"],
        "entry_price": entry_price,
        "hedge_entry_price": hedge_entry_price,
        "current_price": current_price,
        "hedge_current_price": hedge_current_price,
        "entry_date": effective_entry_date,
        "status": "active",
        "trim_status": "untrimmed",
        "trail_stop_level": None,
        "thesis_status": "active",
        "unrealized_pnl_pct": round(main_pnl, 6),
        "hedge_unrealized_pnl_pct": round(hedge_pnl, 6),
        "combined_pnl_pct": round(combined_pnl, 6),
        "daily_change_pct": round(price_history[-1]["daily_change_pct"], 6) if price_history else 0,
        "stop_loss_method": order["stop_loss_method"],
        "take_profit": order["take_profit"],
        "expected_holding_period": order["expected_holding_period"],
        "review_date": order["review_date"],
        "proposal_id": order["proposal_id"],
        "price_history": price_history[-90:],  # Keep last 90 days
    }

    positions.append(position)
    total_allocated += order["size_pct_nav"] * 2  # Both legs

# Update book
book["positions"] = positions
book["cash_pct"] = 1.0 - total_allocated
book["last_marked"] = datetime.now().isoformat()

# Compute NAV change based on position P&L
# NAV = initial_nav + sum(position_pnl * size * initial_nav) for both legs
total_pnl_contribution = sum(
    p["combined_pnl_pct"] * p["size_pct_nav"] * 2  # Both legs contribute
    for p in positions
)
book["nav"] = initial_nav * (1 + total_pnl_contribution)

# Add session_open_nav for circuit breaker
book["session_open_nav"] = book["nav"]

# Write trade journal entries
book["trade_journal"] = []
for pos in positions:
    book["trade_journal"].append({
        "action": "auto_booked",
        "proposal_id": pos["proposal_id"],
        "ticker": pos["ticker"],
        "direction": pos["direction"],
        "entry_price": pos["entry_price"],
        "hedge_entry_price": pos["hedge_entry_price"],
        "size_pct_nav": pos["size_pct_nav"],
        "conviction": pos["conviction"],
        "timestamp": f"{pos['entry_date']}T09:30:00",
    })

# Save book
STATE_FILE.write_text(json.dumps(book, indent=2))

print(f"\n{'=' * 70}")
print(f"BOOK UPDATED")
print(f"{'=' * 70}")
print(f"  Positions booked: {len(positions)}")
print(f"  NAV: ${book['nav']:,.0f} (P&L contribution: {total_pnl_contribution*100:+.3f}%)")
print(f"  Cash: {book['cash_pct']*100:.1f}%")
print(f"  Last marked: {book['last_marked']}")

# Also build NAV history from entry date to today
nav_history = []
if positions and positions[0]["price_history"]:
    for i, day in enumerate(positions[0]["price_history"]):
        # Compute NAV at this date using all positions' price_history at same index
        day_pnl = 0
        for pos in positions:
            if i < len(pos["price_history"]):
                day_pnl += pos["price_history"][i].get("combined_pnl_pct", 0) * pos["size_pct_nav"] * 2
        day_nav = initial_nav * (1 + day_pnl)
        nav_history.append({
            "date": day["date"],
            "nav": round(day_nav, 2),
            "pnl_pct": round(day_pnl, 6),
        })

# Save history
HISTORY_FILE.write_text(json.dumps(nav_history, indent=2))
print(f"  NAV history: {len(nav_history)} days saved to pnl_history.json")

print(f"\n{'═' * 70}")
print(f" BACKFILL COMPLETE")
print(f"{'═' * 70}")
print("Refresh the dashboard to see all positions and performance data.")
