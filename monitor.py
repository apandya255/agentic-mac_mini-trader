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
import re
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService
from trading.slippage import compute_fill_price
from trading.position_states import transition
from trading.sigma_detector import detect_sigma_event, compute_trailing_stddev
from trading.circuit_breaker import compute_progressive_deleverage
from trading.factor_beta import compute_factor_betas, get_alert_level, save_factors, load_factors

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
FACTOR_TICKERS = {"market": "SPY", "energy": "XLE", "tech": "XLK", "healthcare": "XLV"}

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

    # Session-based progressive deleverage (intraday drawdown from session open)
    session_open_nav = book.get("session_open_nav")
    if session_open_nav and session_open_nav > 0:
        deleverage_level = compute_progressive_deleverage(nav, session_open_nav)
        if deleverage_level == "emergency":
            alerts.append(Alert(
                level="critical",
                category="drawdown",
                ticker="PORTFOLIO",
                message=f"EMERGENCY: Intraday drawdown {((nav - session_open_nav) / session_open_nav)*100:.2f}% from session open — close all positions",
                action="IMMEDIATE: Close all positions and halt trading",
            ))
        elif deleverage_level == "deleverage":
            alerts.append(Alert(
                level="critical",
                category="drawdown",
                ticker="PORTFOLIO",
                message=f"DELEVERAGE: Intraday drawdown {((nav - session_open_nav) / session_open_nav)*100:.2f}% from session open",
                action="Close most-losing position, reduce gross exposure",
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


def check_factor_betas(book: dict) -> list:
    """Check factor betas for all active positions and emit alerts."""
    alerts = []
    factors_data = load_factors()

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        ticker = pos.get("ticker", "?")

        results = compute_factor_betas(ticker, price_service, FACTOR_TICKERS)

        for result in results:
            # Update factors state
            factors_data.setdefault(ticker, {})[result.factor_name] = {
                "beta": result.beta,
                "r_squared": result.r_squared,
                "days_used": result.trading_days_used,
                "computed": result.computed_date,
            }

            # Check alert thresholds
            alert_level = get_alert_level(result.beta)
            if alert_level == "critical":
                alerts.append(Alert(
                    level="critical",
                    category="factor",
                    ticker=ticker,
                    message=f"FACTOR BETA CRITICAL: {ticker} has {result.factor_name} beta = {result.beta:.3f} (limit: \u00b1{FACTOR_BETA_LIMIT})",
                    action="Recommend position reduction to lower factor exposure",
                ))
            elif alert_level == "warning":
                alerts.append(Alert(
                    level="warning",
                    category="factor",
                    ticker=ticker,
                    message=f"Factor beta warning: {ticker} has {result.factor_name} beta = {result.beta:.3f} (approaching \u00b1{FACTOR_BETA_LIMIT} limit)",
                    action="Monitor \u2014 consider reducing if beta continues to rise",
                ))

    save_factors(factors_data)
    return alerts


# ──────────────────────────────────────────────────────────────────────────────
# TAKE-PROFIT TRIM & TRAIL STOP LOGIC
# ──────────────────────────────────────────────────────────────────────────────

def parse_take_profit_level(take_profit_str: str) -> float:
    """Parse take profit percentage from string like '5% triggers review'.

    Extracts the first numeric percentage found in the string and returns
    it as a decimal fraction (e.g., '5%' → 0.05).

    Returns 0.05 (5%) as default if no percentage is found.
    """
    if not take_profit_str:
        return 0.05
    match = re.search(r'(\d+(?:\.\d+)?)%', take_profit_str)
    if match:
        return float(match.group(1)) / 100
    return 0.05


def should_trim(position: dict) -> bool:
    """Check if a position should be trimmed (at take-profit, still untrimmed).

    Returns True if:
      - trim_status == "untrimmed"
      - combined_pnl_pct >= take_profit level parsed from position's take_profit field
    """
    if position.get("trim_status", "untrimmed") != "untrimmed":
        return False
    combined_pnl = position.get("combined_pnl_pct")
    if combined_pnl is None:
        return False
    take_profit = parse_take_profit_level(position.get("take_profit", "5%"))
    return combined_pnl >= take_profit


def compute_trail_stop_level(entry_price: float, peak_price: float, direction: str, method: str = "2.5%") -> float:
    """Compute trail stop level based on method.

    For method="2.5%" (default):
      Long:  trail = peak_price * (1 - 0.025)  — 2.5% trailing from peak
      Short: trail = peak_price * (1 + 0.025)  — 2.5% trailing from peak

    For method="50%" (legacy):
      Long:  trail = entry_price + 0.5 * (peak_price - entry_price)  — 50% of gain
      Short: trail = entry_price - 0.5 * (entry_price - peak_price)  — 50% of gain

    Requirements: 7.1, 7.2, 7.4
    """
    if method == "2.5%":
        if direction == "long":
            return peak_price * (1 - 0.025)
        else:  # short
            return peak_price * (1 + 0.025)
    else:  # "50%" legacy method
        if direction == "long":
            return entry_price + 0.5 * (peak_price - entry_price)
        else:  # short
            return entry_price - 0.5 * (entry_price - peak_price)


def ratchet_trail_stop(new_level: float, existing_level: float | None, direction: str) -> float:
    """Enforce monotonic ratchet: trail stop never moves against position.

    For long positions: trail stop only moves up (keep higher value).
    For short positions: trail stop only moves down (keep lower value).

    Requirements: 7.3
    """
    if existing_level is None:
        return new_level
    if direction == "long":
        return max(new_level, existing_level)
    else:  # short
        return min(new_level, existing_level)


def should_trail_stop_close(position: dict) -> bool:
    """Check if a trailed position should be fully closed.

    Returns True if:
      - trail_stop_level is set AND
      - Either:
        - trim_status == "half_trimmed", OR
        - trail_activated == True
      - For long: current_price <= trail_stop_level
      - For short: current_price >= trail_stop_level

    Requirements: 7.1, 7.2, 7.3
    """
    trail_level = position.get("trail_stop_level")
    if trail_level is None:
        return False

    # Trail stop close triggers for half_trimmed positions OR trail_activated positions
    is_half_trimmed = position.get("trim_status") == "half_trimmed"
    is_trail_activated = position.get("trail_activated", False)

    if not is_half_trimmed and not is_trail_activated:
        return False

    current_price = position.get("current_price", 0)
    direction = position.get("direction", "long")

    if direction == "long":
        return current_price <= trail_level
    else:  # short
        return current_price >= trail_level


def execute_trim(position: dict, book: dict) -> None:
    """Execute a 50% take-profit trim on a position.

    - Halves size_pct_nav
    - Sets trim_status to "half_trimmed" via state machine
    - Computes and sets trail_stop_level using position's stop_loss_method
    - Records the partial exit in the trade journal with slippage-adjusted price

    Requirements: 7.1, 7.4
    """
    ticker = position.get("ticker", "?")
    direction = position.get("direction", "long")
    current_price = position.get("current_price")
    entry_price = position.get("entry_price", 0)

    # Compute slippage-adjusted exit price for the trimmed half
    exit_price = compute_fill_price(current_price, direction, "exit")

    # Halve position size
    original_size = position.get("size_pct_nav", 0)
    position["size_pct_nav"] = original_size / 2

    # Transition state machine: untrimmed → half_trimmed
    transition(position, "half_trimmed")

    # Determine trail stop method from position's stop_loss_method
    stop_method = position.get("stop_loss_method", "")
    if "2.5%" in stop_method:
        method = "2.5%"
    else:
        method = "2.5%"  # Default to 2.5% trailing from peak

    # Use current_price as peak_price at trim time (it's the highest so far)
    peak_price = position.get("peak_price", current_price)
    trail_level = compute_trail_stop_level(entry_price, peak_price, direction, method)

    # Apply ratchet enforcement
    trail_level = ratchet_trail_stop(trail_level, position.get("trail_stop_level"), direction)
    position["trail_stop_level"] = trail_level

    # Mark trail as activated
    position["trail_activated"] = True
    position["peak_price"] = peak_price

    # Restore cash for the trimmed half (one leg of pair trade trimmed)
    book["cash_pct"] += original_size  # half of 2x size = original size_pct_nav

    # Log to trade journal
    book.setdefault("trade_journal", []).append({
        "action": "trim",
        "ticker": ticker,
        "direction": direction,
        "exit_price": exit_price,
        "size_trimmed_pct_nav": original_size / 2,
        "remaining_size_pct_nav": position["size_pct_nav"],
        "trail_stop_level": trail_level,
        "realized_pnl_pct": position.get("combined_pnl_pct", 0),
        "reason": "take_profit_trim",
        "timestamp": datetime.now().isoformat(),
    })

    print(f"  ✂ TRIMMED 50%: {ticker} at {position.get('combined_pnl_pct', 0)*100:+.2f}% — trail stop set at ${trail_level:.2f}")


def execute_trail_stop_close(position: dict, book: dict) -> None:
    """Fully close a half-trimmed position that hit its trail stop.

    - Sets status to "closed"
    - Transitions trim_status to "fully_exited"
    - Records exit with slippage-adjusted price and exit_reason="trail_stop_auto"
    """
    ticker = position.get("ticker", "?")
    direction = position.get("direction", "long")
    current_price = position.get("current_price")

    # Compute slippage-adjusted exit price
    exit_price = compute_fill_price(current_price, direction, "exit")

    # Close the position
    position["status"] = "closed"
    position["exit_price"] = exit_price
    position["exit_date"] = date.today().isoformat()
    position["exit_reason"] = "trail_stop_auto"
    position["realized_pnl_pct"] = position.get("combined_pnl_pct", 0)

    # Transition state machine: half_trimmed → fully_exited
    transition(position, "fully_exited")

    # Restore remaining cash (remaining half of 2x size)
    book["cash_pct"] += position.get("size_pct_nav", 0) * 2

    # Log to trade journal
    book.setdefault("trade_journal", []).append({
        "action": "close",
        "ticker": ticker,
        "direction": direction,
        "exit_price": exit_price,
        "realized_pnl_pct": position.get("combined_pnl_pct", 0),
        "reason": "trail_stop_auto",
        "exit_reason": "trail_stop_auto",
        "timestamp": datetime.now().isoformat(),
    })

    print(f"  ✗ TRAIL STOP CLOSED: {ticker} at ${exit_price:.2f} — trail stop breached")


def process_take_profit_and_trail_stops(book: dict) -> tuple[int, int]:
    """Process take-profit trims and trail stop closes for all active positions.

    Also handles trail activation: when P&L first exceeds 0%, activates trailing
    stop and begins tracking peak price.

    Returns (trim_count, trail_close_count).

    Requirements: 7.1, 7.2, 7.3
    """
    trim_count = 0
    trail_close_count = 0

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        # --- Trail activation logic (Requirement 7.1) ---
        # Activate trail stop when P&L first exceeds 0%
        combined_pnl = pos.get("combined_pnl_pct")
        direction = pos.get("direction", "long")
        current_price = pos.get("current_price", 0)
        entry_price = pos.get("entry_price", 0)

        if combined_pnl is not None and not pos.get("trail_activated", False):
            if combined_pnl > 0:
                # First time P&L exceeds 0% — activate trail
                pos["trail_activated"] = True
                pos["peak_price"] = current_price

                # Compute initial trail stop level
                stop_method = pos.get("stop_loss_method", "")
                method = "2.5%" if "2.5%" in stop_method or "50%" not in stop_method else "50%"
                new_level = compute_trail_stop_level(entry_price, current_price, direction, method)
                pos["trail_stop_level"] = ratchet_trail_stop(new_level, pos.get("trail_stop_level"), direction)

        elif pos.get("trail_activated", False):
            # Trail is active — update peak price and ratchet trail stop
            if direction == "long":
                pos["peak_price"] = max(pos.get("peak_price", 0), current_price)
            else:  # short
                pos["peak_price"] = min(pos.get("peak_price", float('inf')), current_price)

            peak_price = pos["peak_price"]
            stop_method = pos.get("stop_loss_method", "")
            method = "2.5%" if "2.5%" in stop_method or "50%" not in stop_method else "50%"
            new_level = compute_trail_stop_level(entry_price, peak_price, direction, method)
            pos["trail_stop_level"] = ratchet_trail_stop(new_level, pos.get("trail_stop_level"), direction)

        # Check for trail stop close first (half_trimmed or trail_activated positions)
        if should_trail_stop_close(pos):
            execute_trail_stop_close(pos, book)
            trail_close_count += 1
            continue

        # Check for take-profit trim (untrimmed positions)
        if should_trim(pos):
            execute_trim(pos, book)
            trim_count += 1

    return trim_count, trail_close_count


# ──────────────────────────────────────────────────────────────────────────────
# THESIS-BREAK DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def parse_holding_period(holding_period_str: str) -> int:
    """
    Parse expected holding period from a string and return the number of days.

    Handles formats like:
      - "30 days" → 30
      - "2-3 weeks" → 21 (uses upper bound)
      - "4 weeks" → 28
      - "1 month" → 30
      - "2 months" → 60
      - "20 trading days" → 20

    Defaults to 60 if unparseable.
    """
    if not holding_period_str:
        return 60

    s = holding_period_str.lower().strip()

    # Try "X days" or "X trading days"
    m = re.search(r'(\d+)\s*(?:trading\s*)?days?', s)
    if m:
        return int(m.group(1))

    # Try range with weeks: "2-3 weeks" → use upper bound × 7
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*weeks?', s)
    if m:
        return int(m.group(2)) * 7

    # Try "X weeks"
    m = re.search(r'(\d+)\s*weeks?', s)
    if m:
        return int(m.group(1)) * 7

    # Try range with months: "1-2 months" → use upper bound × 30
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*months?', s)
    if m:
        return int(m.group(2)) * 30

    # Try "X months"
    m = re.search(r'(\d+)\s*months?', s)
    if m:
        return int(m.group(1)) * 30

    return 60


def check_thesis_break(position: dict, today: date) -> str | None:
    """
    Evaluate thesis-break conditions for a position.

    Checks TWO trigger paths:
    1. Holding period exceeded (original logic)
    2. review_date exceeded and thesis_status != "reviewed" (new, Requirements 9.1)

    Returns:
        "flag_overdue" — holding period or review_date exceeded, should set thesis_status="review_overdue"
        "close" — overdue + negative P&L + overdue > 5 days → close position
        None — no action needed

    Requirements: 5.1, 5.2, 5.3, 9.1, 9.2, 9.3
    """
    thesis_status = position.get("thesis_status", "active")

    # --- Trigger path 2: review_date field check (Requirements 9.1) ---
    review_date_str = position.get("review_date")
    if review_date_str:
        try:
            review_date = date.fromisoformat(review_date_str)
            if today > review_date and thesis_status != "reviewed" and thesis_status != "review_overdue":
                return "flag_overdue"
        except (ValueError, TypeError):
            pass

    # --- Trigger path 1: holding period exceeded (original logic) ---
    entry_date_str = position.get("entry_date")
    if not entry_date_str:
        return None

    try:
        entry_date = date.fromisoformat(entry_date_str)
    except (ValueError, TypeError):
        return None

    # Compute days held
    days_held = (today - entry_date).days

    # Parse expected holding period
    expected_days = parse_holding_period(
        position.get("expected_holding_period", "60 days")
    )

    # Not yet overdue (holding period check)
    if days_held <= expected_days:
        # Even if holding period is fine, check if already review_overdue for close logic
        if thesis_status == "review_overdue":
            return _check_close_conditions(position, today)
        return None

    # Overdue — check current thesis status
    if thesis_status != "review_overdue":
        return "flag_overdue"

    # Already flagged as review_overdue — check close conditions
    return _check_close_conditions(position, today)


def _check_close_conditions(position: dict, today: date) -> str | None:
    """Check if a review_overdue position should be auto-closed.

    Returns "close" if overdue > 5 days with negative P&L, else None.
    """
    overdue_since_str = position.get("overdue_since")
    if not overdue_since_str:
        return None

    try:
        overdue_date = date.fromisoformat(overdue_since_str)
    except (ValueError, TypeError):
        return None

    days_overdue = (today - overdue_date).days
    combined_pnl = position.get("combined_pnl_pct", 0)

    if combined_pnl < 0 and days_overdue > 5:
        return "close"

    return None


def check_thesis_overdue(book: dict) -> list:
    """
    Emit WARNING alerts for all active positions with thesis_status == "review_overdue".

    This ensures overdue positions appear in EVERY monitoring report until manually
    updated (Requirement 9.3).

    Returns list of Alert objects for overdue positions.
    """
    alerts = []
    today = date.today()

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        if pos.get("thesis_status") != "review_overdue":
            continue

        ticker = pos.get("ticker", "?")
        overdue_since = pos.get("overdue_since", "unknown")

        # Compute days overdue
        try:
            overdue_date = date.fromisoformat(overdue_since)
            days = (today - overdue_date).days
        except (ValueError, TypeError):
            days = 0

        alerts.append(Alert(
            level="warning",
            category="holding",
            ticker=ticker,
            message=f"Review overdue: {ticker} — flagged since {overdue_since}, {days} days overdue",
            action="Manually update thesis_status to 'reviewed' after completing review.",
        ))

    return alerts


def process_thesis_breaks(book: dict, no_close: bool = False) -> tuple[list, int]:
    """
    Run thesis-break detection on all active positions.

    Returns a tuple of (alerts, closed_count).

    Requirements: 9.1, 9.2, 9.3
    """
    alerts = []
    closed_count = 0
    today = date.today()

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        result = check_thesis_break(pos, today)

        if result == "flag_overdue":
            pos["thesis_status"] = "review_overdue"
            pos["overdue_since"] = today.isoformat()

            # Compute days_overdue from review_date if available (Requirement 9.2)
            review_date_str = pos.get("review_date")
            if review_date_str:
                try:
                    review_date = date.fromisoformat(review_date_str)
                    days_overdue = (today - review_date).days
                    alert_msg = f"THESIS OVERDUE: {ticker} — review_date {review_date_str} exceeded by {days_overdue} days"
                except (ValueError, TypeError):
                    alert_msg = f"THESIS OVERDUE: {ticker} held beyond expected holding period — flagged for review"
            else:
                alert_msg = f"THESIS OVERDUE: {ticker} held beyond expected holding period — flagged for review"

            alerts.append(Alert(
                level="warning",
                category="holding",
                ticker=ticker,
                message=alert_msg,
                action="Review thesis validity. Auto-close in 5 days if P&L remains negative.",
            ))

            # Telegram dispatch handled centrally in main() (Requirement 9.2)

        elif result == "close" and not no_close:
            # Get slippage-adjusted exit price
            current_price = pos.get("current_price")
            direction = pos.get("direction", "long")

            if current_price is not None:
                exit_price = compute_fill_price(current_price, direction, "exit")
            else:
                exit_price = current_price

            combined_pnl = pos.get("combined_pnl_pct", 0)

            # Close the position
            pos["status"] = "closed"
            pos["exit_price"] = exit_price
            pos["exit_date"] = today.isoformat()
            pos["exit_reason"] = "thesis_break_auto"
            pos["realized_pnl_pct"] = combined_pnl

            # Transition trim status to fully_exited
            try:
                transition(pos, "fully_exited")
            except ValueError:
                pos["trim_status"] = "fully_exited"

            # Restore cash
            book["cash_pct"] = book.get("cash_pct", 0) + pos.get("size_pct_nav", 0) * 2

            # Build thesis summary for journal logging
            thesis_summary = (
                f"Original thesis: {pos.get('proposal_id', 'unknown')}. "
                f"Expected holding: {pos.get('expected_holding_period', 'unknown')}. "
                f"Held {(today - date.fromisoformat(pos.get('entry_date', '2000-01-01'))).days} days. "
                f"P&L at close: {combined_pnl*100:+.2f}%."
            )

            # Log to trade journal
            book.setdefault("trade_journal", []).append({
                "action": "close",
                "ticker": ticker,
                "exit_price": exit_price,
                "realized_pnl_pct": combined_pnl,
                "exit_reason": "thesis_break_auto",
                "thesis_summary": thesis_summary,
                "timestamp": datetime.now().isoformat(),
            })

            alerts.append(Alert(
                level="critical",
                category="thesis_break",
                ticker=ticker,
                message=f"THESIS BREAK CLOSE: {ticker} auto-closed — overdue with negative P&L ({combined_pnl*100:+.2f}%)",
                action=f"Position closed. {thesis_summary}",
            ))

            closed_count += 1
            print(f"  ✗ THESIS-BREAK CLOSE: {ticker} at {combined_pnl*100:+.2f}% (overdue + negative P&L)")

    return alerts, closed_count


# ──────────────────────────────────────────────────────────────────────────────
# SIGMA EVENT DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def check_sigma_events(book: dict) -> tuple[list, list]:
    """
    Detect sigma events (outsized moves) on active positions.

    For each active position with at least 20 days of price_history, compute
    the trailing 20-day standard deviation of daily changes and check if the
    most recent daily change exceeds 2σ.

    Returns:
        Tuple of (alerts, sigma_tickers) where sigma_tickers is a list of
        tickers that triggered a sigma event and need immediate stop-loss
        and take-profit re-evaluation.

    Requirements: 6.1, 6.2, 6.3
    """
    alerts = []
    sigma_tickers = []

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        price_history = pos.get("price_history", [])

        # Need at least 20 days of history for meaningful stddev
        if len(price_history) < 20:
            continue

        # Extract daily_change_pct values from price_history
        daily_changes = [
            h.get("daily_change_pct", 0.0)
            for h in price_history
            if h.get("daily_change_pct") is not None
        ]

        if len(daily_changes) < 20:
            continue

        # Today's change is the most recent entry
        todays_change = daily_changes[-1]
        # Trailing changes exclude today (use previous entries for stddev computation)
        trailing_changes = daily_changes[:-1]

        # Detect sigma event
        event = detect_sigma_event(todays_change, trailing_changes, threshold_sigmas=2.0)

        if event is not None:
            magnitude = event["magnitude"]
            threshold = event["threshold_2sigma"]
            alerts.append(Alert(
                level="critical",
                category="sigma_event",
                ticker=ticker,
                message=f"SIGMA EVENT: {ticker} moved {magnitude*100:+.2f}% "
                        f"(2σ threshold: ±{threshold*100:.2f}%)",
                action="Immediate stop-loss and take-profit re-evaluation triggered",
            ))
            sigma_tickers.append(ticker)

    return alerts, sigma_tickers


# ──────────────────────────────────────────────────────────────────────────────
# AUTO-CLOSE
# ──────────────────────────────────────────────────────────────────────────────

def auto_close_stopped_positions(book: dict, alerts: list) -> int:
    """Close positions that have breached their hard stop.

    Uses slippage-adjusted exit prices, transitions trim_status to
    'fully_exited', restores cash_pct by 2 × size_pct_nav, logs to
    the trade journal with exit_reason="stop_breach", and appends a
    critical alert.

    If the ticker's price data is unavailable (fetch_failed), the stop
    execution is skipped and a WARNING alert is emitted instead.

    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    closed_count = 0

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        if not pos.get("stop_triggered"):
            continue

        ticker = pos.get("ticker", "?")

        # Guard: skip stop execution if price data is unavailable (Requirement 8.4)
        fetch_status = price_service.get_fetch_status(ticker)
        if fetch_status == "fetch_failed":
            alerts.append(Alert(
                level="warning",
                category="stop",
                ticker=ticker,
                message=f"STOP SKIPPED: {ticker} — price data unavailable (fetch_failed), cannot evaluate stop",
                action="Wait for next poll cycle when price data is available",
            ))
            # Clear the stop_triggered flag so it can be re-evaluated next cycle
            pos["stop_triggered"] = False
            print(f"  ⚠ STOP SKIPPED: {ticker} — price data unavailable (fetch_failed)")
            continue

        current_price = pos.get("current_price")
        combined_pnl = pos.get("combined_pnl_pct", 0)
        direction = pos.get("direction", "long")
        size_pct_nav = pos.get("size_pct_nav", 0)

        # Compute slippage-adjusted exit price
        if current_price is not None:
            exit_price = compute_fill_price(current_price, direction, "exit")
        else:
            exit_price = current_price

        # Mark as closed
        pos["status"] = "closed"
        pos["exit_price"] = exit_price
        pos["exit_date"] = date.today().isoformat()
        pos["exit_reason"] = "stop_breach"
        pos["realized_pnl_pct"] = combined_pnl

        # Transition trim_status to fully_exited via state machine
        try:
            transition(pos, "fully_exited")
        except ValueError:
            # If already fully_exited or invalid state, just set it directly
            pos["trim_status"] = "fully_exited"

        # Restore cash: 2 × size_pct_nav for both legs
        book["cash_pct"] = book.get("cash_pct", 0) + size_pct_nav * 2

        # Journal entry with slippage-adjusted exit price (Requirement 8.2)
        book.setdefault("trade_journal", []).append({
            "action": "close",
            "ticker": ticker,
            "exit_price": exit_price,
            "realized_pnl_pct": combined_pnl,
            "exit_reason": "stop_breach",
            "timestamp": datetime.now().isoformat(),
        })

        # Append critical alert for stop-loss closure (Requirement 8.3)
        loss_amount = combined_pnl * size_pct_nav * book.get("nav", 0)
        exit_price_str = f"${exit_price:,.2f}" if exit_price is not None else "N/A"
        alerts.append(Alert(
            level="critical",
            category="stop",
            ticker=ticker,
            message=f"STOP-LOSS CLOSED: {ticker} exited at {exit_price_str} (slippage-adjusted), realized P&L {combined_pnl*100:+.2f}%",
            action=f"Position fully closed. Loss: ${abs(loss_amount):,.0f}",
        ))

        closed_count += 1
        print(f"  ✗ AUTO-CLOSED: {ticker} at {combined_pnl*100:+.2f}% exit_price={exit_price_str} (slippage-adjusted)")

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
    all_alerts.extend(check_factor_betas(book))

    # Sigma event detection
    sigma_alerts, sigma_tickers = check_sigma_events(book)
    all_alerts.extend(sigma_alerts)

    # Trigger immediate stop-loss and take-profit re-evaluation on sigma event positions
    if sigma_tickers and not args.no_close:
        for pos in book.get("positions", []):
            if pos.get("status") != "active":
                continue
            if pos.get("ticker") not in sigma_tickers:
                continue

            ticker = pos.get("ticker", "?")

            # Re-evaluate stop-loss for sigma event positions
            combined_pnl = pos.get("combined_pnl_pct")
            if combined_pnl is not None:
                stop_level = STOP_LOSS_HARD
                stop_method = pos.get("stop_loss_method", "")
                if "2.5%" in stop_method:
                    stop_level = -0.025
                elif "2%" in stop_method:
                    stop_level = -0.02
                elif "3%" in stop_method:
                    stop_level = -0.03

                if combined_pnl <= stop_level:
                    pos["stop_triggered"] = True

            # Re-evaluate take-profit trim for sigma event positions
            if should_trim(pos):
                execute_trim(pos, book)
            elif should_trail_stop_close(pos):
                execute_trail_stop_close(pos, book)

    # Auto-close stopped positions unless --no-close
    closed_count = 0
    if not args.no_close:
        closed_count = auto_close_stopped_positions(book, all_alerts)

    # Process take-profit trims and trail stop closes for all active positions
    trim_count = 0
    trail_close_count = 0
    if not args.no_close:
        trim_count, trail_close_count = process_take_profit_and_trail_stops(book)
        closed_count += trail_close_count

    # Thesis-break detection and auto-close
    thesis_alerts, thesis_closed = process_thesis_breaks(book, no_close=args.no_close)
    all_alerts.extend(thesis_alerts)
    closed_count += thesis_closed

    # Thesis overdue persistent alerts (Requirement 9.3)
    # Surfaces all review_overdue positions in EVERY monitoring report
    overdue_alerts = check_thesis_overdue(book)
    all_alerts.extend(overdue_alerts)

    # Save updated book (if positions were closed, trimmed, or flagged)
    if closed_count > 0 or trim_count > 0 or thesis_alerts or sigma_tickers or overdue_alerts:
        save_book(book)

    # Save alerts
    save_alerts(all_alerts)

    # Dispatch critical and warning alerts via Telegram (Requirements 13.1, 13.4)
    try:
        from telegram_bot import send_message as tg_send
        for alert in all_alerts:
            if alert.level in ("critical", "warning"):
                tg_msg = f"{alert.message}"
                if alert.action:
                    tg_msg += f"\nAction: {alert.action}"
                try:
                    tg_send(tg_msg, severity=alert.level)
                except Exception:
                    pass
    except ImportError:
        pass

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
