#!/usr/bin/env python3
"""
Agentic Trading Dashboard — Live Server

Serves the interactive dashboard with API endpoints for:
  - Viewing portfolio state (book, positions, P&L)
  - Accepting or denying pending trade recommendations
  - Marking positions to market with live prices
  - Tracking NAV history over time

Usage:
    python3 serve.py              # starts on port 8080
    python3 serve.py --port 8080  # custom port
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests as http_requests
from flask import Flask, jsonify, request, send_file

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService
from data_platform.market_calendar import is_market_open

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
CALENDAR_PATH = BASE_DIR / "desk" / "calendar.md"
FACTORS_PATH = BASE_DIR / "memos" / "state" / "factors.json"

# --- Configuration ---
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "5"))

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
    initial_nav = book.get("initial_nav", book.get("nav", 0))
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

    # Add leverage regime from latest risk assessment
    book["leverage_regime"] = None
    if RISK_DIR.exists():
        risk_files = sorted(RISK_DIR.glob("*.json"))
        if risk_files:
            try:
                latest_risk = json.loads(risk_files[-1].read_text())
                book["leverage_regime"] = latest_risk.get("leverage_regime", None)
            except (json.JSONDecodeError, KeyError):
                pass

    # Add staleness indicator
    last_marked = book.get("last_marked")
    if last_marked and is_market_open():
        age_minutes = (datetime.now() - datetime.fromisoformat(last_marked)).total_seconds() / 60
        book["_stale"] = age_minutes > (POLL_INTERVAL_MINUTES + 0.5)
        book["_last_poll_age_minutes"] = round(age_minutes, 1)
    else:
        book["_stale"] = False

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

    # Gather all pipeline data linked to this proposal for the journal
    pid = target.get("proposal_id", "")
    linked_debates = []
    if DEBATE_DIR.exists():
        for f in DEBATE_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                if d.get("proposal_id") == pid:
                    linked_debates.append(d)
            except (json.JSONDecodeError, KeyError):
                continue

    linked_tech = None
    if SCORES_DIR.exists():
        for f in SCORES_DIR.glob("*.json"):
            try:
                s = json.loads(f.read_text())
                if s.get("proposal_id") == pid and s.get("technical_score") is not None:
                    linked_tech = s
                    break
            except (json.JSONDecodeError, KeyError):
                continue

    linked_risk = None
    if RISK_DIR.exists():
        for f in RISK_DIR.glob("*.json"):
            try:
                r = json.loads(f.read_text())
                if r.get("proposal_id") == pid and r.get("decision"):
                    linked_risk = r
                    break
            except (json.JSONDecodeError, KeyError):
                continue

    book["trade_journal"].append({
        "action": "open",
        "order": target,
        "timestamp": datetime.now().isoformat(),
        "entry_price": entry_price,
        "hedge_entry_price": hedge_entry_price,
        "debates": linked_debates,
        "tech_score": linked_tech,
        "risk_decision": linked_risk,
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


@app.route("/api/run-cycle", methods=["POST"])
def api_run_cycle():
    """Trigger a full agent cycle (run_cycle.py) in the background with status tracking."""
    import subprocess
    import threading

    # Status file for progress tracking
    status_path = BASE_DIR / "memos" / "state" / "cycle_status.json"

    def _run():
        status_path.write_text(json.dumps({"running": True, "phase": "Starting...", "started_at": datetime.now().isoformat(), "progress": 0}))
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(BASE_DIR / "run_cycle.py"), "--skip-data"],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.strip()
                # Parse phase markers from run_cycle.py output
                if "PHASE 1" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 1: Refreshing market data...", "progress": 5}))
                elif "PHASE 2" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 2: Agents generating proposals...", "progress": 15}))
                elif "PHASE 3" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 3: Agent debate in progress...", "progress": 40}))
                elif "PHASE 4" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 4: Conviction check...", "progress": 60}))
                elif "PHASE 5" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 5: Technical scoring...", "progress": 70}))
                elif "PHASE 6" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 6: Risk gate evaluation...", "progress": 80}))
                elif "PHASE 7" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 7: PM sizing decisions...", "progress": 90}))
                elif "PHASE 8" in line or "Cycle complete" in line:
                    status_path.write_text(json.dumps({"running": True, "phase": "Phase 8: Finalizing orders...", "progress": 95}))
                elif "Invoking" in line:
                    agent_name = line.split("Invoking")[-1].split("(")[0].strip()
                    current = json.loads(status_path.read_text())
                    current["detail"] = f"Running: {agent_name}"
                    status_path.write_text(json.dumps(current))

            proc.wait(timeout=900)
            status_path.write_text(json.dumps({"running": False, "phase": "Complete", "progress": 100, "finished_at": datetime.now().isoformat()}))
        except Exception as e:
            status_path.write_text(json.dumps({"running": False, "phase": f"Error: {str(e)[:100]}", "progress": 0}))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Agent cycle started. Watch progress on the dashboard."})


@app.route("/api/cycle-status")
def api_cycle_status():
    """Return current cycle run status for the progress overlay."""
    status_path = BASE_DIR / "memos" / "state" / "cycle_status.json"
    if not status_path.exists():
        return jsonify({"running": False, "phase": "Idle", "progress": 0})
    try:
        return jsonify(json.loads(status_path.read_text()))
    except (json.JSONDecodeError, OSError):
        return jsonify({"running": False, "phase": "Idle", "progress": 0})


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


@app.route("/api/calendar")
def api_calendar():
    """Parse desk/calendar.md and return structured JSON."""
    if not CALENDAR_PATH.exists():
        return jsonify({"empty": True, "macro": [], "cb": [], "earnings": [], "holidays": []})
    
    content = CALENDAR_PATH.read_text()
    result = {"empty": True, "macro": [], "cb": [], "earnings": [], "holidays": []}
    
    # Split by ### headers
    current_section = None
    for line in content.split('\n'):
        if line.startswith('### '):
            header = line[4:].strip().lower()
            if 'macro' in header:
                current_section = 'macro'
            elif 'cb' in header or 'decision' in header:
                current_section = 'cb'
            elif 'earning' in header:
                current_section = 'earnings'
            elif 'holiday' in header:
                current_section = 'holidays'
            else:
                current_section = None
        elif current_section and line.strip().startswith('|') and '—' not in line and '---' not in line:
            # Parse table row
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) >= 2 and cells[0] and not all(c == '' or c.startswith('-') for c in cells):
                if current_section == 'macro' and len(cells) >= 3:
                    result['macro'].append({"raw": line.strip()})
                    result['empty'] = False
                elif current_section == 'cb' and len(cells) >= 2:
                    result['cb'].append({"raw": line.strip()})
                    result['empty'] = False
                elif current_section == 'earnings' and len(cells) >= 2:
                    result['earnings'].append({"raw": line.strip()})
                    result['empty'] = False
                elif current_section == 'holidays' and len(cells) >= 2:
                    result['holidays'].append({"raw": line.strip()})
                    result['empty'] = False
    
    return jsonify(result)


@app.route("/api/factors")
def api_factors():
    """Return book-level factor betas. Reads from memos/state/factors.json if available."""
    if not FACTORS_PATH.exists():
        return jsonify({"available": False, "computed_at": None, "factors": {}})
    try:
        data = json.loads(FACTORS_PATH.read_text())
        return jsonify({
            "available": True,
            "computed_at": data.get("computed_at"),
            "factors": data.get("factors", {})
        })
    except (json.JSONDecodeError, KeyError):
        return jsonify({"available": False, "computed_at": None, "factors": {}})


@app.route("/api/logs")
def api_logs():
    """Return all cycle logs from memos/logs/ sorted by timestamp descending."""
    logs = []
    if LOGS_DIR.exists():
        for f in LOGS_DIR.glob("*.json"):
            try:
                log_entry = json.loads(f.read_text())
                logs.append(log_entry)
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by timestamp descending (most recent first)
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(logs)


@app.route("/api/alerts")
def api_alerts():
    """Return alerts (trail breaches, target touches, 2σ interrupts, telegram deliveries) and system health."""
    if not LOGS_DIR.exists():
        return jsonify({"alerts": [], "health": []})

    alerts = []
    health = []
    today = datetime.now().strftime("%Y-%m-%d")

    for log_file in LOGS_DIR.glob("*.json"):
        try:
            entry = json.loads(log_file.read_text())
            cycle_type = entry.get("cycle_type", "")
            timestamp = entry.get("timestamp", "")

            # Alerts: telegram deliveries (these contain trail/target/2σ/feed outage messages)
            if cycle_type == "telegram_delivery":
                alerts.append(entry)
            # Health: price_poll, daily_sweep, full_desk_run from today
            elif timestamp.startswith(today):
                health.append(entry)
        except (json.JSONDecodeError, OSError):
            continue

    alerts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    health.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify({"alerts": alerts[:50], "health": health[:50]})


# ──────────────────────────────────────────────────────────────────────────────
# CHAT AGENT
# ──────────────────────────────────────────────────────────────────────────────

# Load secrets from ~/.openclaw/.env per TOOLS.md security model
from src.data_platform.env_loader import load_secrets
load_secrets()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Chat routes directly through OpenClaw main agent session


def gather_system_context() -> str:
    """Gather all current system state for the chat agent's context."""
    book = load_book()
    active_pos = [p for p in book.get("positions", []) if p.get("status") == "active"]

    # Alerts
    alerts = []
    if ALERTS_PATH.exists():
        alerts = json.loads(ALERTS_PATH.read_text())

    # Recent proposals
    proposals = []
    if PROPOSALS_DIR.exists():
        for f in sorted(PROPOSALS_DIR.glob("*.json"))[-5:]:
            try:
                proposals.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

    # Recent debates
    debates = []
    if DEBATE_DIR.exists():
        for f in sorted(DEBATE_DIR.glob("*.json"))[-5:]:
            try:
                debates.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

    # Recent orders
    orders = []
    if ORDERS_DIR.exists():
        for f in sorted(ORDERS_DIR.glob("order_*.json"))[-3:]:
            try:
                orders.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

    # Cycle logs
    logs = []
    if LOGS_DIR.exists():
        for f in sorted(LOGS_DIR.glob("cycle_*.json"))[-5:]:
            try:
                logs.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

    # NAV history
    history = load_history()[-30:]  # last 30 snapshots

    context = f"""CURRENT PORTFOLIO STATE:
NAV: ${book.get('nav', 10_000_000):,.0f}
Initial NAV: ${book.get('initial_nav', 10_000_000):,.0f}
Total P&L: {((book.get('nav', 10_000_000) - book.get('initial_nav', 10_000_000)) / book.get('initial_nav', 10_000_000)) * 100:+.2f}%
Cash: {book.get('cash_pct', 1.0)*100:.1f}%
Active Positions: {len(active_pos)}
Last Marked: {book.get('last_marked', 'never')}

POSITIONS:
{json.dumps(active_pos, indent=2) if active_pos else 'No active positions.'}

ALERTS:
{json.dumps(alerts, indent=2) if alerts else 'No active alerts.'}

RECENT PROPOSALS (last 5):
{json.dumps(proposals, indent=2) if proposals else 'None.'}

RECENT DEBATES (last 5):
{json.dumps(debates, indent=2) if debates else 'None.'}

RECENT ORDERS (last 3):
{json.dumps(orders, indent=2) if orders else 'None.'}

CYCLE HISTORY (last 5):
{json.dumps(logs, indent=2) if logs else 'None.'}

NAV HISTORY (last 30 snapshots):
{json.dumps(history, indent=2) if history else 'None.'}

TRADE JOURNAL:
{json.dumps(book.get('trade_journal', [])[-10:], indent=2)}
"""
    return context


ALERTS_PATH = BASE_DIR / "memos" / "state" / "alerts.json"


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat directly with the OpenClaw main agent session.
    
    Messages go to the persistent 'main' agent via `openclaw agent`,
    so the agent has memory, tools, skills, and any instruction you give
    persists in the session and influences future behaviour.
    """
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"]

    import subprocess

    cmd = [
        "openclaw", "agent",
        "--agent", "main",
        "--message", user_message,
        "--json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()[:300] if result.stderr else "Unknown error"
            return jsonify({"error": f"OpenClaw agent failed: {stderr}"}), 502

        # Parse JSON response
        import json as json_mod
        try:
            # OpenClaw may print debug lines before JSON — find the JSON start
            stdout = result.stdout
            json_start = stdout.find("{")
            if json_start < 0:
                return jsonify({"answer": stdout.strip()[:2000] or "No response"})
            stdout = stdout[json_start:]
            
            response_data = json_mod.loads(stdout)
            answer = ""

            # Try payloads at top level (openclaw agent --json format)
            if "payloads" in response_data and response_data["payloads"]:
                answer = "\n".join(
                    p.get("text", "") for p in response_data["payloads"] if p.get("text")
                )
            # Try nested under result
            elif "result" in response_data:
                r = response_data["result"]
                if "payloads" in r and r["payloads"]:
                    answer = "\n".join(
                        p.get("text", "") for p in r["payloads"] if p.get("text")
                    )
                elif r.get("finalAssistantVisibleText"):
                    answer = r["finalAssistantVisibleText"]
            # Try top-level fields
            elif response_data.get("finalAssistantVisibleText"):
                answer = response_data["finalAssistantVisibleText"]

            if not answer:
                answer = "Agent returned no text response."

            return jsonify({"answer": answer})
        except json_mod.JSONDecodeError:
            # If not JSON, return raw output
            return jsonify({"answer": result.stdout.strip()[:2000] or "No response"})

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Agent timed out (120s)"}), 504
    except Exception as e:
        return jsonify({"error": f"Failed to reach OpenClaw: {str(e)}"}), 502


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS (continued)
# ──────────────────────────────────────────────────────────────────────────────

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
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
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
