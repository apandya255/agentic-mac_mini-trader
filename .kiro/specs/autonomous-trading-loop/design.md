# Design Document: Autonomous Trading Loop

## Architecture Overview

The Autonomous Trading Loop converts the existing human-in-the-loop pipeline into a fully autonomous paper-trading system. The design modifies four existing modules (`run_cycle.py`, `monitor.py`, `serve.py`, `dashboard.py`) and adds scheduling infrastructure via macOS `launchd` plists.

```
┌──────────────────────────────────────────────────────────────────┐
│                      SCHEDULER (launchd)                          │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐  │
│  │ Pipeline Slots (4x)  │   │ Monitor Polling (every 5 min)    │  │
│  │ 9:40, 11:30, 1:30,  │   │ + Sigma Event Trigger            │  │
│  │ 3:30 ET              │   │                                  │  │
│  └──────────┬───────────┘   └──────────────┬───────────────────┘  │
└─────────────┼──────────────────────────────┼─────────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────┐   ┌──────────────────────────────────┐
│    run_cycle.py          │   │         monitor.py                │
│  Phase 1-7: unchanged    │   │  + Take-profit trim (50% + trail)│
│  Phase 8: AUTO-BOOK      │   │  + Trail stop logic              │
│    ├─ Gate validation    │   │  + Thesis-break detection        │
│    ├─ Circuit breaker    │   │  + 2σ event detection            │
│    ├─ Slippage model     │   │  + Slippage-adjusted exits       │
│    └─ Journal logging    │   │  + Position state machine        │
└──────────────┬───────────┘   └──────────────┬───────────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   memos/state/book.json                            │
│  + session_open_nav (circuit breaker reference)                   │
│  + position.trim_status (untrimmed|half_trimmed|fully_exited)     │
│  + position.trail_stop_level (trailing stop price)                │
│  + position.thesis_status (active|review_overdue)                 │
│  + position.overdue_since (date when flagged overdue)             │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│              serve.py / dashboard.html                             │
│  + /api/accept, /api/deny → HTTP 403                             │
│  + /api/close → disabled                                         │
│  + Autonomous mode banner                                        │
│  + Circuit breaker indicator                                     │
│  + All read endpoints unchanged                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Slippage Model (`src/trading/slippage.py`)

A pure function module that computes slippage-adjusted fill prices.

```python
import os

def get_slippage_bps() -> int:
    """Read slippage from environment, default 5 bps."""
    return int(os.environ.get("SLIPPAGE_BPS", "5"))


def compute_fill_price(last_observed_price: float, direction: str, side: str, slippage_bps: int | None = None) -> float:
    """
    Compute slippage-adjusted fill price.
    
    Args:
        last_observed_price: Last observed market close price.
        direction: "long" or "short" — the position direction.
        side: "entry" or "exit" — whether we're entering or exiting.
        slippage_bps: Override slippage in basis points. If None, reads from env.
    
    Returns:
        Adjusted fill price (always adverse to the trader).
    
    Slippage is adverse to the trade direction:
        - Long entry: price goes UP (pay more)     → price × (1 + bps/10000)
        - Short entry: price goes DOWN (sell less)  → price × (1 - bps/10000)
        - Long exit: price goes DOWN (receive less) → price × (1 - bps/10000)
        - Short exit: price goes UP (buy back more) → price × (1 + bps/10000)
    """
    if slippage_bps is None:
        slippage_bps = get_slippage_bps()
    
    factor = slippage_bps / 10000
    
    if direction == "long" and side == "entry":
        return last_observed_price * (1 + factor)
    elif direction == "short" and side == "entry":
        return last_observed_price * (1 - factor)
    elif direction == "long" and side == "exit":
        return last_observed_price * (1 - factor)
    elif direction == "short" and side == "exit":
        return last_observed_price * (1 + factor)
    else:
        raise ValueError(f"Invalid direction/side: {direction}/{side}")
```

### 2. Gate Validator (`src/trading/gate_validator.py`)

Pure function that validates all three pipeline gate conditions.

```python
from dataclasses import dataclass


@dataclass
class GateResult:
    passed: bool
    failing_gate: str | None = None  # "conviction", "risk", or "pm_execute"


def validate_gates(conviction: int | float, risk_decision: str, pm_execute: bool) -> GateResult:
    """
    Validate all three pipeline gate conditions.
    
    Returns GateResult with passed=True if all gates clear,
    or passed=False with the first failing gate identified.
    """
    if conviction < 5:
        return GateResult(passed=False, failing_gate="conviction")
    if risk_decision not in ("approved", "approved_with_modifications"):
        return GateResult(passed=False, failing_gate="risk")
    if not pm_execute:
        return GateResult(passed=False, failing_gate="pm_execute")
    return GateResult(passed=True)
```

### 3. Circuit Breaker (`src/trading/circuit_breaker.py`)

Manages session-open NAV and intraday drawdown threshold.

```python
from datetime import datetime, time
from pathlib import Path
import json

DRAWDOWN_THRESHOLD = -0.02  # -2%


@dataclass
class CircuitBreakerState:
    active: bool
    session_open_nav: float
    current_drawdown: float


def compute_intraday_drawdown(current_nav: float, session_open_nav: float) -> float:
    """Compute intraday drawdown as a fraction (negative means loss)."""
    if session_open_nav <= 0:
        return 0.0
    return (current_nav - session_open_nav) / session_open_nav


def is_circuit_breaker_active(current_nav: float, session_open_nav: float) -> CircuitBreakerState:
    """
    Check if circuit breaker should be active.
    Active when intraday drawdown exceeds -2%.
    """
    drawdown = compute_intraday_drawdown(current_nav, session_open_nav)
    return CircuitBreakerState(
        active=(drawdown <= DRAWDOWN_THRESHOLD),
        session_open_nav=session_open_nav,
        current_drawdown=drawdown,
    )


def reset_session_nav(book_path: Path) -> float:
    """
    Record session-open NAV at 9:30 AM ET.
    Returns the session-open NAV value.
    """
    book = json.loads(book_path.read_text())
    session_nav = book.get("nav", 0)
    book["session_open_nav"] = session_nav
    book_path.write_text(json.dumps(book, indent=2))
    return session_nav
```

### 4. Position State Machine (`src/trading/position_states.py`)

Manages the trim_status field and valid transitions.

```python
VALID_TRANSITIONS = {
    "untrimmed": ["half_trimmed", "fully_exited"],
    "half_trimmed": ["fully_exited"],
    "fully_exited": [],
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """Check if a trim_status transition is valid."""
    return to_state in VALID_TRANSITIONS.get(from_state, [])


def transition(position: dict, to_state: str) -> dict:
    """
    Apply a trim_status transition to a position.
    Raises ValueError if the transition is invalid.
    """
    current = position.get("trim_status", "untrimmed")
    if not is_valid_transition(current, to_state):
        raise ValueError(f"Invalid transition: {current} → {to_state}")
    position["trim_status"] = to_state
    return position
```

### 5. Sigma Event Detector (`src/trading/sigma_detector.py`)

Computes trailing volatility and detects outsized moves.

```python
import math


def compute_trailing_stddev(daily_changes: list[float]) -> float:
    """
    Compute standard deviation of the last 20 daily_change_pct values.
    Returns 0.0 if fewer than 2 data points.
    """
    data = daily_changes[-20:]
    n = len(data)
    if n < 2:
        return 0.0
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / (n - 1)  # sample stddev
    return math.sqrt(variance)


def detect_sigma_event(daily_change_pct: float, trailing_20d_changes: list[float], threshold_sigmas: float = 2.0) -> dict | None:
    """
    Detect if today's move exceeds the 2σ threshold.
    
    Returns event dict if triggered, None otherwise.
    """
    stddev = compute_trailing_stddev(trailing_20d_changes)
    if stddev == 0.0:
        return None
    
    threshold = threshold_sigmas * stddev
    if abs(daily_change_pct) > threshold:
        return {
            "triggered": True,
            "magnitude": daily_change_pct,
            "threshold_2sigma": threshold,
            "trailing_stddev": stddev,
        }
    return None
```

### 6. Take-Profit & Trail Stop Logic (in `monitor.py`)

```python
def compute_trail_stop_level(entry_price: float, current_price: float, direction: str) -> float:
    """
    After 50% trim, set trail stop at 50% of unrealized gain from entry.
    
    For a long position with entry=100, current=106 (6% gain):
      trail stop = 106 - (106 - 100) * 0.5 = 106 - 3 = 103
      (protects 50% of the gain)
    
    For a short position with entry=100, current=94 (6% gain):
      trail stop = 94 + (100 - 94) * 0.5 = 94 + 3 = 97
      (protects 50% of the gain)
    """
    if direction == "long":
        gain = current_price - entry_price
        return current_price - (gain * 0.5)
    else:  # short
        gain = entry_price - current_price
        return current_price + (gain * 0.5)


def should_trim(position: dict) -> bool:
    """Check if a position should be trimmed (at take-profit, still untrimmed)."""
    if position.get("trim_status", "untrimmed") != "untrimmed":
        return False
    combined_pnl = position.get("combined_pnl_pct")
    if combined_pnl is None:
        return False
    
    # Parse take-profit level from position
    take_profit = parse_take_profit_level(position.get("take_profit", "5%"))
    return combined_pnl >= take_profit


def should_trail_stop_close(position: dict) -> bool:
    """Check if a trailed position should be fully closed."""
    if position.get("trim_status") != "half_trimmed":
        return False
    trail_level = position.get("trail_stop_level")
    if trail_level is None:
        return False
    
    current_price = position.get("current_price", 0)
    direction = position.get("direction", "long")
    
    if direction == "long":
        return current_price <= trail_level
    else:  # short
        return current_price >= trail_level


def parse_take_profit_level(take_profit_str: str) -> float:
    """Parse take profit percentage from string like '5% triggers review'."""
    import re
    match = re.search(r'(\d+(?:\.\d+)?)%', take_profit_str)
    if match:
        return float(match.group(1)) / 100
    return 0.05  # default 5%
```

### 7. Thesis-Break Detection (in `monitor.py`)

```python
from datetime import date


def check_thesis_break(position: dict, today: date) -> str | None:
    """
    Evaluate thesis-break conditions.
    
    Returns:
        "flag_overdue" — if holding period exceeded, should set thesis_status
        "close" — if overdue + negative P&L for > 5 days, should close
        None — no action needed
    """
    entry_date = date.fromisoformat(position.get("entry_date", "2000-01-01"))
    
    # Parse expected holding period (e.g., "20 trading days", "4 weeks")
    expected_days = parse_holding_period(position.get("expected_holding_period", "60 days"))
    days_held = (today - entry_date).days
    
    # Check if overdue
    if days_held <= expected_days:
        return None
    
    # Check if already flagged
    thesis_status = position.get("thesis_status", "active")
    if thesis_status != "review_overdue":
        return "flag_overdue"
    
    # Already flagged — check if negative P&L for > 5 trading days
    overdue_since = position.get("overdue_since")
    if overdue_since is None:
        return None
    
    overdue_date = date.fromisoformat(overdue_since)
    days_overdue = (today - overdue_date).days
    combined_pnl = position.get("combined_pnl_pct", 0)
    
    if combined_pnl < 0 and days_overdue > 5:
        return "close"
    
    return None
```

### 8. Auto-Booker (modified Phase 8 in `run_cycle.py`)

```python
def phase_8_auto_book(orders: list[dict]) -> None:
    """
    Phase 8: Autonomous booking.
    
    For each order that clears all gates:
      1. Check circuit breaker
      2. Validate gates (conviction ≥ 5, risk approved, PM execute)
      3. Compute slippage-adjusted entry price
      4. Add position to book
      5. Reduce cash by 2x size (both legs)
      6. Log full provenance to trade journal
    """
    from src.trading.slippage import compute_fill_price
    from src.trading.gate_validator import validate_gates
    from src.trading.circuit_breaker import is_circuit_breaker_active
    
    book = load_book()
    session_open_nav = book.get("session_open_nav", book.get("nav", 0))
    
    # Check circuit breaker
    cb_state = is_circuit_breaker_active(book["nav"], session_open_nav)
    
    for order in orders:
        # Gate validation
        gate_result = validate_gates(
            conviction=order.get("conviction", 0),
            risk_decision=order.get("risk_decision", {}).get("decision", ""),
            pm_execute=order.get("execute", False),
        )
        
        if not gate_result.passed:
            # Log rejection
            book["trade_journal"].append({
                "action": "auto_rejected",
                "proposal_id": order.get("proposal_id"),
                "failing_gate": gate_result.failing_gate,
                "timestamp": datetime.now().isoformat(),
            })
            continue
        
        # Circuit breaker check
        if cb_state.active:
            order["status"] = "circuit_breaker_held"
            # Persist held order
            order_path = ORDERS_DIR / f"{order['order_id']}_held.json"
            order_path.write_text(json.dumps(order, indent=2))
            book["trade_journal"].append({
                "action": "circuit_breaker_held",
                "proposal_id": order.get("proposal_id"),
                "drawdown": cb_state.current_drawdown,
                "timestamp": datetime.now().isoformat(),
            })
            continue
        
        # Compute fill prices
        ticker = order.get("ticker", "")
        hedge_ticker = order.get("hedge_ticker", "")
        direction = order.get("direction", "long")
        hedge_direction = order.get("hedge_direction", "short")
        
        last_price = get_price(ticker)
        hedge_last_price = get_price(hedge_ticker) if hedge_ticker else None
        
        entry_price = compute_fill_price(last_price, direction, "entry")
        hedge_entry_price = compute_fill_price(hedge_last_price, hedge_direction, "entry") if hedge_last_price else None
        
        # Build position
        position = {
            "ticker": ticker,
            "direction": direction,
            "hedge_ticker": hedge_ticker,
            "hedge_direction": hedge_direction,
            "size_pct_nav": order.get("size_pct_nav", 0.03),
            "conviction": order.get("conviction", 7),
            "entry_price": entry_price,
            "hedge_entry_price": hedge_entry_price,
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "trim_status": "untrimmed",
            "trail_stop_level": None,
            "thesis_status": "active",
            "stop_loss_method": order.get("stop_loss_method", "trailing 2.5%"),
            "take_profit": order.get("take_profit", "5%"),
            "expected_holding_period": order.get("expected_holding_period", "60 days"),
            "proposal_id": order.get("proposal_id", ""),
            "price_history": [],
        }
        
        # Update book
        book["positions"].append(position)
        book["cash_pct"] -= position["size_pct_nav"] * 2
        
        # Log full provenance
        book["trade_journal"].append({
            "action": "auto_booked",
            "proposal_id": order.get("proposal_id"),
            "ticker": ticker,
            "direction": direction,
            "entry_price": entry_price,
            "size_pct_nav": position["size_pct_nav"],
            "conviction": order.get("conviction"),
            "tech_score": order.get("_tech_score"),
            "risk_decision": order.get("risk_decision"),
            "pm_rationale": order.get("pm_rationale"),
            "debate_results": order.get("_debates"),
            "timestamp": datetime.now().isoformat(),
        })
    
    save_book(book)
```

### 9. Dashboard Read-Only Mode (modified `serve.py`)

```python
# Replace the existing accept/deny/close endpoints:

@app.route("/api/accept/<order_id>", methods=["POST"])
def api_accept(order_id: str):
    """Disabled in autonomous mode."""
    return jsonify({
        "error": "autonomous_mode_active",
        "message": "Manual trade approval is disabled in autonomous mode"
    }), 403


@app.route("/api/deny/<order_id>", methods=["POST"])
def api_deny(order_id: str):
    """Disabled in autonomous mode."""
    return jsonify({
        "error": "autonomous_mode_active",
        "message": "Manual trade approval is disabled in autonomous mode"
    }), 403


@app.route("/api/close/<ticker>", methods=["POST"])
def api_close(ticker: str):
    """Disabled in autonomous mode."""
    return jsonify({
        "error": "autonomous_mode_active",
        "message": "Manual position close is disabled in autonomous mode"
    }), 403
```

### 10. Scheduler Plists

Four pipeline slots plus one monitor polling plist:

**`com.agentic-trader.pipeline-0940.plist`**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentic-trader.pipeline-0940</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/.venv/bin/python3</string>
        <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/run_cycle.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>40</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/memos/logs/launchd_pipeline.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/memos/logs/launchd_pipeline_err.log</string>
</dict>
</plist>
```

Additional plists follow same structure for 11:30, 13:30, 15:30 slots.

**`com.agentic-trader.monitor.plist`** (5-minute interval):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentic-trader.monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/.venv/bin/python3</string>
        <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/monitor.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader</string>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/memos/logs/launchd_monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/memos/logs/launchd_monitor_err.log</string>
</dict>
</plist>
```

**`com.agentic-trader.session-reset.plist`** (9:30 AM NAV snapshot):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentic-trader.session-reset</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader/.venv/bin/python3</string>
        <string>-c</string>
        <string>from src.trading.circuit_breaker import reset_session_nav; from pathlib import Path; reset_session_nav(Path("memos/state/book.json"))</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/clawbot/Desktop/agentic trading/agentic-mac_mini-trader</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
</dict>
</plist>
```

### 11. Overlap Guard (`src/trading/overlap_guard.py`)

Prevents concurrent pipeline executions via a lock file.

```python
import os
import fcntl
from pathlib import Path
from contextlib import contextmanager

LOCK_PATH = Path(__file__).parent.parent.parent / "memos" / "state" / "pipeline.lock"


@contextmanager
def pipeline_lock():
    """
    Acquire an exclusive file lock for the pipeline.
    Raises RuntimeError if another cycle is already running.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        yield
    except BlockingIOError:
        lock_fd.close()
        raise RuntimeError("cycle_skipped_overlap")
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
```

## Data Models

### Extended Position Schema

```python
position = {
    # Existing fields (unchanged)
    "ticker": str,
    "direction": str,          # "long" or "short"
    "hedge_ticker": str,
    "hedge_direction": str,
    "size_pct_nav": float,
    "conviction": int,
    "entry_price": float,
    "hedge_entry_price": float,
    "entry_date": str,         # ISO date
    "status": str,             # "active", "closed"
    "stop_loss_method": str,
    "take_profit": str,
    "proposal_id": str,
    "price_history": list,
    
    # New fields for autonomous loop
    "trim_status": str,          # "untrimmed" | "half_trimmed" | "fully_exited"
    "trail_stop_level": float | None,  # Set after 50% trim
    "thesis_status": str,        # "active" | "review_overdue"
    "overdue_since": str | None, # ISO date when flagged overdue
    "expected_holding_period": str,
    "exit_reason": str | None,   # "stop_loss_auto" | "trail_stop_auto" | "thesis_break_auto"
}
```

### Extended Book Schema

```python
book = {
    # Existing fields (unchanged)
    "nav": float,
    "initial_nav": float,
    "cash_pct": float,
    "positions": list,
    "trade_journal": list,
    
    # New fields
    "session_open_nav": float,   # Set at 9:30 AM for circuit breaker
}
```

### Trade Journal Entry Schema (Auto-Book)

```python
journal_entry_booked = {
    "action": "auto_booked",
    "proposal_id": str,
    "ticker": str,
    "direction": str,
    "entry_price": float,
    "size_pct_nav": float,
    "conviction": int,
    "tech_score": dict | None,
    "risk_decision": dict,
    "pm_rationale": str,
    "debate_results": list | None,
    "timestamp": str,
}

journal_entry_rejected = {
    "action": "auto_rejected",
    "proposal_id": str,
    "failing_gate": str,    # "conviction" | "risk" | "pm_execute"
    "timestamp": str,
}

journal_entry_exit = {
    "action": "close",
    "ticker": str,
    "exit_price": float,
    "realized_pnl_pct": float,
    "exit_reason": str,     # "stop_loss_auto" | "trail_stop_auto" | "thesis_break_auto"
    "thesis_summary": str | None,  # included for thesis_break exits
    "timestamp": str,
}
```

## Interfaces

### Slippage Model Interface

| Function | Input | Output |
|----------|-------|--------|
| `compute_fill_price(price, direction, side, bps)` | `float, str, str, int?` | `float` |
| `get_slippage_bps()` | — | `int` |

### Gate Validator Interface

| Function | Input | Output |
|----------|-------|--------|
| `validate_gates(conviction, risk_decision, pm_execute)` | `int, str, bool` | `GateResult` |

### Circuit Breaker Interface

| Function | Input | Output |
|----------|-------|--------|
| `compute_intraday_drawdown(nav, session_open_nav)` | `float, float` | `float` |
| `is_circuit_breaker_active(nav, session_open_nav)` | `float, float` | `CircuitBreakerState` |
| `reset_session_nav(book_path)` | `Path` | `float` |

### Position State Machine Interface

| Function | Input | Output |
|----------|-------|--------|
| `is_valid_transition(from_state, to_state)` | `str, str` | `bool` |
| `transition(position, to_state)` | `dict, str` | `dict` |

### Sigma Detector Interface

| Function | Input | Output |
|----------|-------|--------|
| `compute_trailing_stddev(daily_changes)` | `list[float]` | `float` |
| `detect_sigma_event(daily_change, trailing_changes, threshold)` | `float, list[float], float` | `dict? ` |

## Error Handling

| Scenario | Handling |
|----------|----------|
| Price service returns None for a ticker | Skip that position/order, log warning, do not book |
| Circuit breaker active during booking | Hold orders with status "circuit_breaker_held", skip booking |
| Gate validation fails | Reject order, log with specific failing gate |
| Lock file indicates concurrent cycle | Skip cycle, log "cycle_skipped_overlap" event |
| Book file corrupted/unreadable | Abort cycle, log critical alert, preserve existing file |
| SLIPPAGE_BPS env var contains non-integer | Fall back to default of 5 bps, log warning |
| Trailing stddev is 0 (no variance in 20-day history) | Do not trigger sigma event (avoid division by zero) |
| Position has no price_history for sigma check | Skip sigma detection for that position |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Slippage is always adverse to the trader

*For any* trade fill with a valid direction (long/short) and side (entry/exit), the slippage-adjusted price SHALL be strictly worse for the trader than the unadjusted last observed price. Specifically: long entries cost more, short entries receive less, long exits receive less, short exits cost more.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

### Property 2: Gate validation is conjunction of all three conditions

*For any* order with arbitrary conviction score, risk decision string, and PM execute boolean, the order SHALL be booked if and only if (conviction ≥ 5) AND (risk_decision ∈ {"approved", "approved_with_modifications"}) AND (pm_execute = true). If any condition fails, the order SHALL be rejected with the specific failing gate identified.

**Validates: Requirements 1.1, 10.1, 10.2, 10.3, 10.4**

### Property 3: Circuit breaker activates at exactly the -2% threshold

*For any* pair of current NAV and session-open NAV values where session_open_nav > 0, the circuit breaker SHALL be active if and only if (current_nav - session_open_nav) / session_open_nav ≤ -0.02. When active, no orders shall be booked; they shall be persisted with status "circuit_breaker_held".

**Validates: Requirements 2.1, 2.2**

### Property 4: Cash accounting is consistent through booking

*For any* book state with cash_pct ∈ [0, 1] and any position with size_pct_nav > 0, after booking the position the book's cash_pct SHALL equal the original cash_pct minus 2 × size_pct_nav (accounting for both legs of the pair trade).

**Validates: Requirements 1.4**

### Property 5: Stop-loss closure restores cash and records exit

*For any* active position whose combined_pnl_pct breaches its stop-loss level, after the Position_Monitor processes it: (a) the position status SHALL be "closed", (b) the exit_price SHALL be slippage-adjusted, (c) cash_pct SHALL increase by 2 × size_pct_nav, (d) the trade journal SHALL contain an entry with exit_reason = "stop_loss_auto", and (e) alerts.json SHALL contain a critical-level entry with the ticker.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 6: Take-profit trim halves position and sets trail stop

*For any* active position with trim_status = "untrimmed" and combined_pnl_pct ≥ take_profit level, after the Position_Monitor trims it: (a) size_pct_nav SHALL be reduced by exactly 50%, (b) trim_status SHALL be "half_trimmed", and (c) trail_stop_level SHALL be set at current_price minus 50% of the gain from entry (for longs) or current_price plus 50% of the gain from entry (for shorts).

**Validates: Requirements 4.1, 4.2, 4.4**

### Property 7: Trail stop closure fully exits the remainder

*For any* position with trim_status = "half_trimmed" and a defined trail_stop_level, when the current price retraces past the trail stop (price ≤ trail_stop for longs, price ≥ trail_stop for shorts), the Position_Monitor SHALL close the position fully with trim_status = "fully_exited" and exit_reason = "trail_stop_auto".

**Validates: Requirements 4.3, 4.4**

### Property 8: Trim status state machine only moves forward

*For any* position, the trim_status field SHALL only transition through the sequence "untrimmed" → "half_trimmed" → "fully_exited". No backwards transitions or state skips (except untrimmed → fully_exited for stop-loss/thesis-break closures) SHALL be permitted.

**Validates: Requirements 4.4**

### Property 9: Thesis-break closure requires both conditions

*For any* active position, the Position_Monitor SHALL close it with exit_reason = "thesis_break_auto" if and only if: (a) the position has been held beyond its expected_holding_period (flagged as review_overdue), AND (b) combined_pnl_pct < 0, AND (c) the position has been flagged review_overdue for more than 5 trading days.

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 10: Sigma event detection is symmetric and threshold-based

*For any* position with at least 20 days of price history, the sigma event detector SHALL trigger if and only if |daily_change_pct| > 2 × trailing_20day_stddev. The trailing standard deviation SHALL be computed as the sample standard deviation of the last 20 daily_change_pct values.

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 11: Read-only API enforcement

*For any* POST request to /api/accept/{id} or /api/deny/{id}, the server SHALL return HTTP 403 with body {"error": "autonomous_mode_active", "message": "Manual trade approval is disabled in autonomous mode"}. All GET endpoints (/api/book, /api/history, /api/pending, /api/alerts, /api/factors, /api/mark) SHALL continue to return HTTP 200 with valid JSON.

**Validates: Requirements 8.3, 8.5**

### Property 12: Pipeline overlap guard ensures mutual exclusion

*For any* two concurrent pipeline cycle triggers, at most one SHALL execute. The second SHALL be skipped with a logged "cycle_skipped_overlap" event.

**Validates: Requirements 7.5**

### Property 13: Auto-booked positions include full provenance

*For any* successfully auto-booked position, the corresponding trade journal entry SHALL contain all provenance fields: proposal_id, debate_results, tech_score, risk_decision, and pm_rationale (or pm_sizing). No provenance field SHALL be omitted.

**Validates: Requirements 1.3**
