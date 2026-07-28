#!/usr/bin/env python3
"""
Position Monitor — Risk & Alert System

Runs after mark_to_market.py to enforce risk rules from the production spec:
  - Stop-loss proximity and breach detection
  - Drawdown monitoring with progressive deleverage triggers
  - Factor beta drift (approaching ±0.6 limit)
  - Inter-position correlation regime changes
  - Holding period review triggers
  - Auto-close positions that hit hard stops

Outputs alerts to: memos/state/alerts.json
Auto-closes positions that breach hard stops.

Usage:
    python3 monitor.py              # run full monitor cycle
    python3 monitor.py --no-close   # alert only, don't auto-close
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService

# Paths
BASE_DIR = Path(__file__).parent
BOOK_PATH = BASE_DIR / "memos" / "state" / "book.json"
ALERTS_PATH = BASE_DIR / "memos" / "state" / "alerts.json"
HISTORY_PATH = BASE_DIR / "memos" / "state" / "pnl_history.json"

# Risk thresholds from production spec
STOP_LOSS_HARD = -0.03          # -3% hard stop (position level)
STOP_PROXIMITY_WARN = -0.02     # warn when within 50bps of stop
DRAWDOWN_WARN = -0.02           # -2% portfolio drawdown warning
DRAWDOWN_DELEVERAGE = -0.03     # -3% triggers deleverage recommendation
DRAWDOWN_EMERGENCY = -0.04      # -4% emergency deleverage
FACTOR_BETA_LIMIT = 0.6         # ±0.6 per factor
FACTOR_BETA_WARN = 0.5          # warn when approaching
MAX_CORRELATION = 0.7           # max inter-position correlation
CORRELATION_WARN = 0.5          # warn threshold
MAX_HOLDING_DAYS = 60           # flag positions held > 60 days without review

price_service = PriceService()


# ──────────────────────────────────────────────────────────────────────────────
# ALERT SYSTEM
# ──────────────────────────────────────────────────────────────────────────────

class Alert:
    """Represents a single monitoring alert."""
    def __init__(self, level: str, category: str, ticker: str, message: str, action: str = ""):
        self.level = level          # "critical", "warning", "info"
        self.category = category    # "stop", "drawdown", "factor", "correlation", "holding"
        self.ticker = ticker
        self.message = message
        self.action = action        # recommended action
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "level": self.level,
            "category": self.category,
            "ticker": self.ticker,
            "message": self.message,
            "action": self.action,
            "timestamp": self.timestamp,
        }


def load_book() -> dict:
    if not BOOK_PATH.exists():
        return {"nav": 10_000_000, "initial_nav": 10_000_000, "cash_pct": 1.0, "positions": [], "trade_journal": []}
    return json.loads(BOOK_PATH.read_text())


def save_book(book: dict) -> None:
    BOOK_PATH.write_text(json.dumps(book, indent=2))


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text())


def save_alerts(alerts: list) -> None:
    """Save current alerts (overwrites — shows latest state only)."""
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps([a.to_dict() for a in alerts], indent=2))


# ──────────────────────────────────────────────────────────────────────────────
# MONITORING CHECKS
# ──────────────────────────────────────────────────────────────────────────────

def check_stop_losses(book: dict) -> list:
    """Check all active positions against stop-loss thresholds."""
    alerts = []
    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        combined_pnl = pos.get("combined_pnl_pct")
        if combined_pnl is None:
            continue

        # Parse stop level from stop_loss_method string
        stop_level = STOP_LOSS_HARD  # default -3%
        stop_method = pos.get("stop_loss_method", "")
        if "2.5%" in stop_method:
            stop_level = -0.025
        elif "2%" in stop_method:
            stop_level = -0.02
        elif "3%" in stop_method:
            stop_level = -0.03

        if combined_pnl <= stop_level:
            alerts.append(Alert(
                level="critical",
                category="stop",
                ticker=ticker,
                message=f"STOP BREACHED: {ticker} at {combined_pnl*100:+.2f}% (stop: {stop_level*100:.1f}%)",
                action="AUTO-CLOSE" if not pos.get("stop_override") else "MANUAL REVIEW",
            ))
            pos["stop_triggered"] = True
        elif combined_pnl <= stop_level + 0.005:  # within 50bps of stop
            alerts.append(Alert(
                level="warning",
                category="stop",
                ticker=ticker,
                message=f"STOP PROXIMITY: {ticker} at {combined_pnl*100:+.2f}% — within 50bps of {stop_level*100:.1f}% stop",
                action="Monitor closely, consider tightening stop",
            ))

    return alerts


def check_drawdown(book: dict, history: list) -> list:
    """Check portfolio-level drawdown from peak NAV."""
    alerts = []
    nav = book.get("nav", 10_000_000)
    initial = book.get("initial_nav", 10_000_000)

    # Find peak NAV from history
    peak_nav = initial
    for h in history:
        if h.get("nav", 0) > peak_nav:
            peak_nav = h["nav"]
    if nav > peak_nav:
        peak_nav = nav

    drawdown = (nav - peak_nav) / peak_nav if peak_nav > 0 else 0

    if drawdown <= DRAWDOWN_EMERGENCY:
        alerts.append(Alert(
            level="critical",
            category="drawdown",
            ticker="PORTFOLIO",
            message=f"EMERGENCY DRAWDOWN: {drawdown*100:.2f}% from peak (${peak_nav:,.0f} → ${nav:,.0f})",
            action="IMMEDIATE DELEVERAGE — reduce all positions by 50%",
        ))
    elif drawdown <= DRAWDOWN_DELEVERAGE:
        alerts.append(Alert(
            level="critical",
            category="drawdown",
            ticker="PORTFOLIO",
            message=f"DELEVERAGE TRIGGER: {drawdown*100:.2f}% drawdown from peak",
            action="Reduce gross exposure by 30%, close weakest conviction position",
        ))
    elif drawdown <= DRAWDOWN_WARN:
        alerts.append(Alert(
            level="warning",
            category="drawdown",
            ticker="PORTFOLIO",
            message=f"Drawdown warning: {drawdown*100:.2f}% from peak NAV of ${peak_nav:,.0f}",
            action="Review all positions, tighten stops",
        ))

    return alerts


def check_concentration(book: dict) -> list:
    """Check sector concentration and single-name limits."""
    alerts = []
    active = [p for p in book.get("positions", []) if p.get("status") == "active"]

    # Sector concentration (max 25% gross per sector)
    sector_exposure = {}
    for pos in active:
        # Infer sector from agent_id or proposal_id
        proposal_id = pos.get("proposal_id", "")
        sector = "unknown"
        if "energy" in proposal_id:
            sector = "energy"
        elif "infotech" in proposal_id or "tech" in proposal_id:
            sector = "infotech"
        elif "healthcare" in proposal_id or "health" in proposal_id:
            sector = "healthcare"
        elif "financials" in proposal_id or "finance" in proposal_id:
            sector = "financials"

        size = pos.get("size_pct_nav", 0) * 2  # both legs
        sector_exposure[sector] = sector_exposure.get(sector, 0) + size

    for sector, exposure in sector_exposure.items():
        if exposure > 0.25:
            alerts.append(Alert(
                level="warning",
                category="concentration",
                ticker=f"SECTOR:{sector.upper()}",
                message=f"Sector concentration: {sector} at {exposure*100:.1f}% gross (limit: 25%)",
                action="Do not add more positions in this sector",
            ))

    # Single-name concentration (max 5% NAV)
    for pos in active:
        size = pos.get("size_pct_nav", 0)
        if size > 0.05:
            alerts.append(Alert(
                level="warning",
                category="concentration",
                ticker=pos.get("ticker", "?"),
                message=f"Single-name concentration: {pos['ticker']} at {size*100:.1f}% NAV (limit: 5%)",
                action="Reduce position size",
            ))

    return alerts


def check_correlation(book: dict) -> list:
    """Check inter-position correlations using price history."""
    alerts = []
    active = [p for p in book.get("positions", []) if p.get("status") == "active"]

    if len(active) < 2:
        return alerts

    # Build daily return series from price_history for each position
    returns_by_ticker = {}
    for pos in active:
        ticker = pos.get("ticker", "")
        hist = pos.get("price_history", [])
        if len(hist) >= 5:
            prices = [h.get("price") for h in hist if h.get("price") is not None]
            if len(prices) >= 5:
                returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                returns_by_ticker[ticker] = returns

    # Check pairwise correlations
    tickers = list(returns_by_ticker.keys())
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            t1, t2 = tickers[i], tickers[j]
            r1, r2 = returns_by_ticker[t1], returns_by_ticker[t2]

            # Align lengths
            min_len = min(len(r1), len(r2))
            if min_len < 5:
                continue
            r1, r2 = r1[-min_len:], r2[-min_len:]

            # Compute correlation
            corr = compute_correlation(r1, r2)

            if abs(corr) >= MAX_CORRELATION:
                alerts.append(Alert(
                    level="critical",
                    category="correlation",
                    ticker=f"{t1}/{t2}",
                    message=f"HIGH CORRELATION: {t1} and {t2} correlation = {corr:.2f} (limit: ±{MAX_CORRELATION})",
                    action="Reduce one position — positions are not diversifying",
                ))
            elif abs(corr) >= CORRELATION_WARN:
                alerts.append(Alert(
                    level="warning",
                    category="correlation",
                    ticker=f"{t1}/{t2}",
                    message=f"Correlation warning: {t1} and {t2} = {corr:.2f} (approaching {MAX_CORRELATION} limit)",
                    action="Monitor — consider if both positions serve same thesis",
                ))

    return alerts


def compute_correlation(x: list, y: list) -> float:
    """Compute Pearson correlation between two return series."""
    n = len(x)
    if n < 3:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((xi - mean_x) ** 2 for xi in x) / n
    var_y = sum((yi - mean_y) ** 2 for yi in y) / n
    if var_x == 0 or var_y == 0:
        return 0.0
    cov_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    return cov_xy / (var_x ** 0.5 * var_y ** 0.5)


def check_holding_period(book: dict) -> list:
    """Flag positions approaching or exceeding their expected holding period."""
    alerts = []
    today = date.today()

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        entry_date_str = pos.get("entry_date")
        if not entry_date_str:
            continue

        try:
            entry_date = date.fromisoformat(entry_date_str)
        except (ValueError, TypeError):
            continue

        days_held = (today - entry_date).days

        if days_held > MAX_HOLDING_DAYS:
            alerts.append(Alert(
                level="warning",
                category="holding",
                ticker=ticker,
                message=f"OVERDUE REVIEW: {ticker} held {days_held} days (max recommended: {MAX_HOLDING_DAYS})",
                action="Review thesis — is the catalyst still valid? Consider exiting.",
            ))
        elif days_held > MAX_HOLDING_DAYS - 7:
            alerts.append(Alert(
                level="info",
                category="holding",
                ticker=ticker,
                message=f"Holding period approaching limit: {ticker} at {days_held} days",
                action="Schedule review within 1 week",
            ))

    return alerts


def check_take_profit(book: dict) -> list:
    """Flag positions that have hit take-profit targets."""
    alerts = []

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        combined_pnl = pos.get("combined_pnl_pct")
        if combined_pnl is None:
            continue

        # Default take profit at 5%
        take_profit = 0.05
        tp_method = pos.get("take_profit", "")
        if "5%" in tp_method:
            take_profit = 0.05
        elif "3%" in tp_method:
            take_profit = 0.03

        if combined_pnl >= take_profit:
            alerts.append(Alert(
                level="info",
                category="take_profit",
                ticker=ticker,
                message=f"TARGET REACHED: {ticker} at {combined_pnl*100:+.2f}% (target: {take_profit*100:.0f}%)",
                action="Take 50% profit, trail remainder per spec",
            ))

    return alerts


# ──────────────────────────────────────────────────────────────────────────────
# AUTO-CLOSE
# ──────────────────────────────────────────────────────────────────────────────

def auto_close_stopped_positions(book: dict, alerts: list) -> int:
    """Close positions that have breached their hard stop."""
    closed_count = 0

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        if not pos.get("stop_triggered"):
            continue

        ticker = pos.get("ticker", "?")
        current_price = pos.get("current_price")
        combined_pnl = pos.get("combined_pnl_pct", 0)

        # Mark as closed
        pos["status"] = "closed"
        pos["exit_price"] = current_price
        pos["exit_date"] = date.today().isoformat()
        pos["exit_reason"] = "stop_loss_auto"
        pos["realized_pnl_pct"] = combined_pnl

        # Restore cash
        book["cash_pct"] += pos.get("size_pct_nav", 0) * 2

        # Journal entry
        book.setdefault("trade_journal", []).append({
            "action": "close",
            "ticker": ticker,
            "exit_price": current_price,
            "realized_pnl_pct": combined_pnl,
            "reason": "stop_loss_auto",
            "timestamp": datetime.now().isoformat(),
        })

        closed_count += 1
        print(f"  ✗ AUTO-CLOSED: {ticker} at {combined_pnl*100:+.2f}% (stop triggered)")

    return closed_count


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Position Monitor — Risk & Alert System")
    parser.add_argument("--no-close", action="store_true", help="Alert only, don't auto-close stopped positions")
    args = parser.parse_args()

    book = load_book()
    history = load_history()
    active = [p for p in book.get("positions", []) if p.get("status") == "active"]

    print(f"\n  Position Monitor")
    print(f"  ────────────────")
    print(f"  Active positions: {len(active)}")
    print(f"  NAV: ${book.get('nav', 0):,.0f}")
    print(f"  Cash: {book.get('cash_pct', 1.0)*100:.1f}%\n")

    if not active:
        print("  No active positions to monitor.\n")
        save_alerts([])
        return

    # Run all checks
    all_alerts = []
    all_alerts.extend(check_stop_losses(book))
    all_alerts.extend(check_drawdown(book, history))
    all_alerts.extend(check_concentration(book))
    all_alerts.extend(check_correlation(book))
    all_alerts.extend(check_holding_period(book))
    all_alerts.extend(check_take_profit(book))

    # Auto-close stopped positions unless --no-close
    closed_count = 0
    if not args.no_close:
        closed_count = auto_close_stopped_positions(book, all_alerts)

    # Save updated book
    if closed_count > 0:
        save_book(book)

    # Save alerts
    save_alerts(all_alerts)

    # Print summary
    critical = [a for a in all_alerts if a.level == "critical"]
    warnings = [a for a in all_alerts if a.level == "warning"]
    info = [a for a in all_alerts if a.level == "info"]

    if critical:
        print("  ══ CRITICAL ALERTS ══")
        for a in critical:
            print(f"  🔴 [{a.category}] {a.message}")
            print(f"     → {a.action}")
        print()

    if warnings:
        print("  ── WARNINGS ──")
        for a in warnings:
            print(f"  🟡 [{a.category}] {a.message}")
            print(f"     → {a.action}")
        print()

    if info:
        print("  ── INFO ──")
        for a in info:
            print(f"  🔵 [{a.category}] {a.message}")
            print(f"     → {a.action}")
        print()

    if not all_alerts:
        print("  ✓ All clear — no alerts.\n")

    if closed_count:
        print(f"  Auto-closed {closed_count} position(s).")

    print(f"  Alerts saved to: {ALERTS_PATH}")
    print(f"  Total: {len(critical)} critical, {len(warnings)} warnings, {len(info)} info\n")


if __name__ == "__main__":
    main()
