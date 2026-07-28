#!/usr/bin/env python3
"""
Agentic Trading Dashboard — Live Server

Serves the interactive dashboard with API endpoints for:
  - Viewing portfolio state (book, positions, P&L)
  - Accepting or denying pending trade recommendations
  - Marking positions to market with live prices
  - Tracking NAV history over time

Usage:
    python3 serve.py              # starts on port 5100
    python3 serve.py --port 8080  # custom port
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService

# --- Paths ---
BASE_DIR = Path(__file__).parent
BOOK_PATH = BASE_DIR / "memos" / "state" / "book.json"
ORDERS_DIR = BASE_DIR / "memos" / "orders"
PROPOSALS_DIR = BASE_DIR / "memos" / "proposals"
DEBATE_DIR = BASE_DIR / "memos" / "debate"
RISK_DIR = BASE_DIR / "memos" / "risk"
SCORES_DIR = BASE_DIR / "memos" / "scores"
LOGS_DIR = BASE_DIR / "memos" / "logs"
HISTORY_PATH = BASE_DIR / "memos" / "state" / "pnl_history.json"
DASHBOARD_PATH = BASE_DIR / "dashboard.html"

app = Flask(__name__)
price_service = PriceService()


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def load_book() -> dict:
    if not BOOK_PATH.exists():
        default = {"nav": 10_000_000, "initial_nav": 10_000_000, "cash_pct": 1.0,
                   "positions": [], "trade_journal": []}
        BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        BOOK_PATH.write_text(json.dumps(default, indent=2))
        return default
    return json.loads(BOOK_PATH.read_text())


def save_book(book: dict) -> None:
    BOOK_PATH.write_text(json.dumps(book, indent=2))


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text())


def save_history(history: list) -> None:
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def get_pending_orders() -> list:
    """Orders that have execute=true but whose proposal_id is NOT in the book's positions or journal."""
    book = load_book()

    # Collect all proposal_ids already in the book
    booked_ids = set()
    for pos in book.get("positions", []):
        if pos.get("proposal_id"):
            booked_ids.add(pos["proposal_id"])
    for entry in book.get("trade_journal", []):
        if "order" in entry and entry["order"].get("proposal_id"):
            booked_ids.add(entry["order"]["proposal_id"])
        if entry.get("proposal_id"):
            booked_ids.add(entry["proposal_id"])

    # Also check denied orders
    denied_path = BASE_DIR / "memos" / "state" / "denied.json"
    denied_ids = set()
    if denied_path.exists():
        denied_ids = set(json.loads(denied_path.read_text()))

    pending = []
    if ORDERS_DIR.exists():
        for f in sorted(ORDERS_DIR.glob("order_*.json")):
            try:
                order = json.loads(f.read_text())
                pid = order.get("proposal_id", "")
                if order.get("execute") and pid not in booked_ids and pid not in denied_ids:
                    order["_file"] = f.name
                    pending.append(order)
            except (json.JSONDecodeError, KeyError):
                continue
    return pending


def get_price(ticker: str):
    """Get latest close price."""
    try:
        return price_service.get_latest_close(ticker)
    except Exception:
        return None


def mark_positions_to_market(book: dict) -> dict:
    """Update all positions with current prices and compute P&L."""
    today = datetime.now().strftime("%Y-%m-%d")

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "")
        hedge_ticker = pos.get("hedge_ticker", "")

        current = get_price(ticker)
        hedge_current = get_price(hedge_ticker) if hedge_ticker else None

        if current is not None:
            pos["current_price"] = current
        if hedge_current is not None:
            pos["hedge_current_price"] = hedge_current

        # Compute unrealized P&L
        entry = pos.get("entry_price")
        direction = pos.get("direction", "long")
        if entry and current:
            if direction == "long":
                pos["unrealized_pnl_pct"] = (current - entry) / entry
            else:
                pos["unrealized_pnl_pct"] = (entry - current) / entry
        else:
            pos["unrealized_pnl_pct"] = None

        # Hedge P&L
        hedge_entry = pos.get("hedge_entry_price")
        hedge_dir = pos.get("hedge_direction", "short")
        if hedge_entry and hedge_current:
            if hedge_dir == "short":
                pos["hedge_unrealized_pnl_pct"] = (hedge_entry - hedge_current) / hedge_entry
            else:
                pos["hedge_unrealized_pnl_pct"] = (hedge_current - hedge_entry) / hedge_entry
        else:
            pos["hedge_unrealized_pnl_pct"] = None

        # Combined P&L
        main_pnl = pos.get("unrealized_pnl_pct")
        hedge_pnl = pos.get("hedge_unrealized_pnl_pct")
        if main_pnl is not None and hedge_pnl is not None:
            pos["combined_pnl_pct"] = (main_pnl + hedge_pnl) / 2
        elif main_pnl is not None:
            pos["combined_pnl_pct"] = main_pnl
        else:
            pos["combined_pnl_pct"] = None

        # ── Per-position daily price history ──
        if "price_history" not in pos:
            pos["price_history"] = []

        prev_close = pos["price_history"][-1].get("price") if pos["price_history"] else None
        if current is not None and prev_close is not None and prev_close != 0:
            daily_chg = (current - prev_close) / prev_close
        else:
            daily_chg = 0.0

        daily_record = {
            "date": today,
            "price": current,
            "hedge_price": hedge_current,
            "combined_pnl_pct": pos.get("combined_pnl_pct"),
            "daily_change_pct": daily_chg,
        }

        if pos["price_history"] and pos["price_history"][-1].get("date") == today:
            pos["price_history"][-1] = daily_record
        else:
            pos["price_history"].append(daily_record)

        pos["price_history"] = pos["price_history"][-90:]
        pos["daily_change_pct"] = daily_chg

    # Update NAV based on positions P&L
    initial_nav = book.get("initial_nav", 10_000_000)
    total_pnl_dollars = 0
    for pos in book.get("positions", []):
        combined = pos.get("combined_pnl_pct")
        size = pos.get("size_pct_nav", 0)
        if combined is not None:
            total_pnl_dollars += combined * size * initial_nav

    book["nav"] = initial_nav + total_pnl_dollars
    book["last_marked"] = datetime.now().isoformat()
    return book


# ──────────────────────────────────────────────────────────────────────────────
# API ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serve the dashboard HTML."""
    # Regenerate dashboard before serving
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "dashboard.py"), "--no-open"], capture_output=True)
    return send_file(str(DASHBOARD_PATH))


@app.route("/api/book")
def api_book():
    """Return current book state with live prices."""
    book = load_book()
    book = mark_positions_to_market(book)
    save_book(book)
    return jsonify(book)


@app.route("/api/pending")
def api_pending():
    """Return pending orders awaiting accept/deny."""
    pending = get_pending_orders()

    # Enrich with proposal data
    for order in pending:
        pid = order.get("proposal_id", "")
        # Load proposal thesis
        for pf in PROPOSALS_DIR.glob("*.json"):
            try:
                prop = json.loads(pf.read_text())
                if prop.get("proposal_id") == pid:
                    order["_proposal"] = prop
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        # Load tech score
        for sf in SCORES_DIR.glob(f"*{pid}*"):
            try:
                order["_tech_score"] = json.loads(sf.read_text())
                break
            except (json.JSONDecodeError, KeyError):
                continue
        # Load risk decision
        for rf in RISK_DIR.glob(f"*{pid}*"):
            try:
                order["_risk"] = json.loads(rf.read_text())
                break
            except (json.JSONDecodeError, KeyError):
                continue

    return jsonify({"pending": pending, "count": len(pending)})


@app.route("/api/accept/<order_id>", methods=["POST"])
def api_accept(order_id: str):
    """Accept a pending order — adds it to the book at current market price."""
    # Find the order
    pending = get_pending_orders()
    target = None
    for o in pending:
        if o.get("order_id") == order_id or o.get("proposal_id") == order_id:
            target = o
            break

    if not target:
        return jsonify({"error": "Order not found or already processed"}), 404

    # Get current prices for entry
    ticker = target.get("ticker", "")
    hedge_ticker = target.get("hedge_ticker", "")
    entry_price = get_price(ticker)
    hedge_entry_price = get_price(hedge_ticker) if hedge_ticker else None

    if entry_price is None:
        return jsonify({"error": f"Cannot get price for {ticker}"}), 400

    # Build position
    position = {
        "ticker": ticker,
        "direction": target.get("direction", "long"),
        "hedge_ticker": hedge_ticker,
        "hedge_direction": target.get("hedge_direction", "short"),
        "pair_ratio": round(entry_price / hedge_entry_price, 4) if hedge_entry_price else None,
        "size_pct_nav": target.get("size_pct_nav", 0.02),
        "conviction": target.get("conviction", 7),
        "entry_price": entry_price,
        "hedge_entry_price": hedge_entry_price,
        "current_price": entry_price,
        "hedge_current_price": hedge_entry_price,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "active",
        "stop_loss_method": target.get("stop_loss_method", "trailing 2.5%"),
        "take_profit": target.get("take_profit", ""),
        "proposal_id": target.get("proposal_id", ""),
        "unrealized_pnl_pct": 0.0,
        "hedge_unrealized_pnl_pct": 0.0,
        "combined_pnl_pct": 0.0,
    }

    # Update book
    book = load_book()
    book["positions"].append(position)
    book["cash_pct"] -= position["size_pct_nav"] * 2  # both legs
    book["trade_journal"].append({
        "action": "open",
        "order": target,
        "timestamp": datetime.now().isoformat(),
        "entry_price": entry_price,
        "hedge_entry_price": hedge_entry_price,
    })
    save_book(book)

    # Record NAV snapshot
    record_nav_snapshot(book)

    return jsonify({
        "status": "accepted",
        "ticker": ticker,
        "entry_price": entry_price,
        "hedge_entry_price": hedge_entry_price,
        "position": position,
    })


@app.route("/api/deny/<order_id>", methods=["POST"])
def api_deny(order_id: str):
    """Deny a pending order — marks it as rejected."""
    pending = get_pending_orders()
    target = None
    for o in pending:
        if o.get("order_id") == order_id or o.get("proposal_id") == order_id:
            target = o
            break

    if not target:
        return jsonify({"error": "Order not found or already processed"}), 404

    # Add to denied list
    denied_path = BASE_DIR / "memos" / "state" / "denied.json"
    denied = []
    if denied_path.exists():
        denied = json.loads(denied_path.read_text())
    denied.append(target.get("proposal_id", order_id))
    denied_path.write_text(json.dumps(denied, indent=2))

    # Log to journal
    book = load_book()
    book["trade_journal"].append({
        "action": "denied",
        "order": target,
        "timestamp": datetime.now().isoformat(),
        "reason": request.json.get("reason", "User denied") if request.is_json else "User denied",
    })
    save_book(book)

    return jsonify({"status": "denied", "proposal_id": target.get("proposal_id")})


@app.route("/api/close/<ticker>", methods=["POST"])
def api_close(ticker: str):
    """Close an active position at current market price."""
    book = load_book()
    target_pos = None
    for pos in book.get("positions", []):
        if pos.get("ticker") == ticker and pos.get("status") == "active":
            target_pos = pos
            break

    if not target_pos:
        return jsonify({"error": f"No active position for {ticker}"}), 404

    # Get exit prices
    exit_price = get_price(ticker)
    hedge_exit = get_price(target_pos.get("hedge_ticker", "")) if target_pos.get("hedge_ticker") else None

    # Compute realized P&L
    entry = target_pos.get("entry_price", 0)
    direction = target_pos.get("direction", "long")
    if direction == "long":
        realized_pnl = (exit_price - entry) / entry if entry else 0
    else:
        realized_pnl = (entry - exit_price) / entry if entry else 0

    # Mark position closed
    target_pos["status"] = "closed"
    target_pos["exit_price"] = exit_price
    target_pos["hedge_exit_price"] = hedge_exit
    target_pos["exit_date"] = datetime.now().strftime("%Y-%m-%d")
    target_pos["realized_pnl_pct"] = realized_pnl

    # Restore cash
    book["cash_pct"] += target_pos.get("size_pct_nav", 0) * 2

    # Journal
    book["trade_journal"].append({
        "action": "close",
        "ticker": ticker,
        "exit_price": exit_price,
        "realized_pnl_pct": realized_pnl,
        "timestamp": datetime.now().isoformat(),
    })

    save_book(book)
    record_nav_snapshot(book)

    return jsonify({
        "status": "closed",
        "ticker": ticker,
        "exit_price": exit_price,
        "realized_pnl_pct": realized_pnl,
    })


@app.route("/api/mark")
def api_mark():
    """Trigger mark-to-market refresh."""
    book = load_book()
    book = mark_positions_to_market(book)
    save_book(book)
    record_nav_snapshot(book)
    return jsonify({"status": "marked", "nav": book["nav"], "last_marked": book.get("last_marked")})


@app.route("/api/history")
def api_history():
    """Return NAV history for equity curve charting."""
    history = load_history()
    return jsonify({"history": history})


@app.route("/api/debates")
def api_debates():
    """Return debate memos."""
    debates = []
    if DEBATE_DIR.exists():
        for f in sorted(DEBATE_DIR.glob("*.json")):
            try:
                debates.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue
    return jsonify({"debates": debates})


@app.route("/api/risk")
def api_risk():
    """Return risk assessments."""
    risks = []
    if RISK_DIR.exists():
        for f in sorted(RISK_DIR.glob("*.json")):
            try:
                risks.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue
    return jsonify({"risks": risks})


@app.route("/api/scores")
def api_scores():
    """Return technical scores."""
    scores = []
    if SCORES_DIR.exists():
        for f in sorted(SCORES_DIR.glob("*.json")):
            try:
                scores.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue
    return jsonify({"scores": scores})


@app.route("/api/logs")
def api_logs():
    """Return cycle logs."""
    logs = []
    if LOGS_DIR.exists():
        for f in sorted(LOGS_DIR.glob("cycle_*.json")):
            try:
                logs.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue
    return jsonify({"logs": logs})


def record_nav_snapshot(book: dict) -> None:
    """Record a point in NAV history."""
    history = load_history()
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "nav": book.get("nav", 10_000_000),
        "positions": len([p for p in book.get("positions", []) if p.get("status") == "active"]),
        "cash_pct": book.get("cash_pct", 1.0),
    }
    # Avoid duplicate snapshots for same minute
    if history and history[-1].get("timestamp", "")[:16] == snapshot["timestamp"][:16]:
        history[-1] = snapshot
    else:
        history.append(snapshot)
    save_history(history)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic Trading Dashboard Server")
    parser.add_argument("--port", type=int, default=5100, help="Port to run on (default: 5100)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    print(f"\n  Agentic Trading Dashboard")
    print(f"  ─────────────────────────")
    print(f"  Running on: http://{args.host}:{args.port}")
    print(f"  Dashboard:  http://{args.host}:{args.port}/")
    print(f"  API docs:   GET /api/book, /api/pending, /api/history, /api/mark")
    print(f"              POST /api/accept/<id>, /api/deny/<id>, /api/close/<ticker>")
    print(f"  Press Ctrl+C to quit\n")

    app.run(host=args.host, port=args.port, debug=False)
