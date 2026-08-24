# Implementation Plan: Autonomous Trading Loop

## Overview

Convert the existing human-in-the-loop trading pipeline into a fully autonomous paper-trading system. This involves creating new pure-function modules (slippage, gate validation, circuit breaker, position states, sigma detection, overlap guard), modifying existing modules (run_cycle.py Phase 8, monitor.py, serve.py, dashboard.py), and adding launchd scheduling infrastructure.

## Tasks

- [x] 1. Create core trading utility modules
  - [x] 1.1 Implement slippage model (`src/trading/slippage.py`)
    - Create `src/trading/__init__.py` and `src/trading/slippage.py`
    - Implement `get_slippage_bps()` reading from SLIPPAGE_BPS env var, defaulting to 5
    - Implement `compute_fill_price(last_observed_price, direction, side, slippage_bps)` with adverse slippage logic
    - Long entry: price × (1 + bps/10000), short entry: price × (1 - bps/10000)
    - Long exit: price × (1 - bps/10000), short exit: price × (1 + bps/10000)
    - Raise ValueError for invalid direction/side combinations
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 1.2 Implement gate validator (`src/trading/gate_validator.py`)
    - Create `GateResult` dataclass with `passed: bool` and `failing_gate: str | None`
    - Implement `validate_gates(conviction, risk_decision, pm_execute)` returning GateResult
    - Gate conditions: conviction ≥ 5, risk_decision in ("approved", "approved_with_modifications"), pm_execute is True
    - Return first failing gate if any condition fails
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 1.3 Implement circuit breaker (`src/trading/circuit_breaker.py`)
    - Create `CircuitBreakerState` dataclass with `active`, `session_open_nav`, `current_drawdown`
    - Implement `compute_intraday_drawdown(current_nav, session_open_nav)` returning fraction
    - Implement `is_circuit_breaker_active(current_nav, session_open_nav)` activating at -2% threshold
    - Implement `reset_session_nav(book_path)` to record session-open NAV from book
    - Handle edge case where session_open_nav ≤ 0
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 1.4 Implement position state machine (`src/trading/position_states.py`)
    - Define `VALID_TRANSITIONS` dict: untrimmed → [half_trimmed, fully_exited], half_trimmed → [fully_exited], fully_exited → []
    - Implement `is_valid_transition(from_state, to_state)` → bool
    - Implement `transition(position, to_state)` raising ValueError on invalid transitions
    - _Requirements: 4.4_

  - [x] 1.5 Implement sigma event detector (`src/trading/sigma_detector.py`)
    - Implement `compute_trailing_stddev(daily_changes)` using last 20 values, sample stddev
    - Return 0.0 if fewer than 2 data points
    - Implement `detect_sigma_event(daily_change_pct, trailing_20d_changes, threshold_sigmas=2.0)`
    - Return event dict with triggered, magnitude, threshold_2sigma, trailing_stddev if |change| > threshold
    - Return None if no event or stddev is 0
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 1.6 Implement overlap guard (`src/trading/overlap_guard.py`)
    - Implement `pipeline_lock()` context manager using `fcntl.flock` with LOCK_EX | LOCK_NB
    - Lock file at `memos/state/pipeline.lock`
    - Raise RuntimeError("cycle_skipped_overlap") if lock cannot be acquired
    - Write PID to lock file while held
    - _Requirements: 7.5_

- [x] 2. Write property tests for core modules
  - [x] 2.1 Write property test for slippage model
    - **Property 1: Slippage is always adverse to the trader**
    - For any valid direction/side, slippage-adjusted price is strictly worse than unadjusted price
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

  - [x] 2.2 Write property test for gate validator
    - **Property 2: Gate validation is conjunction of all three conditions**
    - Order booked iff conviction ≥ 5 AND risk approved AND pm_execute = True
    - **Validates: Requirements 1.1, 10.1, 10.2, 10.3, 10.4**

  - [x] 2.3 Write property test for circuit breaker
    - **Property 3: Circuit breaker activates at exactly the -2% threshold**
    - Active iff (current_nav - session_open_nav) / session_open_nav ≤ -0.02
    - **Validates: Requirements 2.1, 2.2**

  - [x] 2.4 Write property test for position state machine
    - **Property 8: Trim status state machine only moves forward**
    - Only valid transitions: untrimmed → half_trimmed → fully_exited (plus untrimmed → fully_exited)
    - **Validates: Requirements 4.4**

  - [x] 2.5 Write property test for sigma event detector
    - **Property 10: Sigma event detection is symmetric and threshold-based**
    - Trigger iff |daily_change_pct| > 2 × trailing_20day_stddev
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 3. Checkpoint — Core modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Modify `run_cycle.py` for autonomous Phase 8 booking
  - [x] 4.1 Replace Phase 8 with auto-booking logic
    - Import from `src.trading.slippage`, `src.trading.gate_validator`, `src.trading.circuit_breaker`
    - Wrap cycle execution with `pipeline_lock()` from overlap guard
    - For each order: validate gates, check circuit breaker, compute slippage-adjusted fill, add to book
    - Reduce `cash_pct` by `size_pct_nav × 2` for both legs
    - Persist circuit-breaker-held orders with status "circuit_breaker_held"
    - Log full provenance to trade journal (proposal_id, debate_results, tech_score, risk_decision, pm_rationale)
    - Log rejections with `action = "auto_rejected"` and specific failing gate
    - Initialize new position fields: trim_status="untrimmed", trail_stop_level=None, thesis_status="active"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 10.1, 10.2, 10.3, 10.4_

  - [x] 4.2 Write property test for cash accounting
    - **Property 4: Cash accounting is consistent through booking**
    - After booking: cash_pct = original - 2 × size_pct_nav
    - **Validates: Requirements 1.4**

  - [x] 4.3 Write property test for provenance logging
    - **Property 13: Auto-booked positions include full provenance**
    - Journal entry SHALL contain proposal_id, debate_results, tech_score, risk_decision, pm_rationale
    - **Validates: Requirements 1.3**

- [x] 5. Modify `monitor.py` for automated exit logic
  - [x] 5.1 Implement take-profit trim and trail stop logic
    - Add `parse_take_profit_level(take_profit_str)` to extract percentage from string
    - Add `should_trim(position)` — returns True if untrimmed and combined_pnl_pct ≥ take-profit
    - Add `compute_trail_stop_level(entry_price, current_price, direction)` — 50% of gain from entry
    - Add `should_trail_stop_close(position)` — returns True if half_trimmed and price retraces past trail
    - Integrate trim logic into monitor loop: halve size_pct_nav, set trim_status="half_trimmed", set trail_stop_level
    - Integrate trail stop close: set status="closed", trim_status="fully_exited", exit_reason="trail_stop_auto"
    - Apply slippage-adjusted exit prices using `compute_fill_price`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 Implement thesis-break detection
    - Add `parse_holding_period(holding_period_str)` to extract expected days
    - Add `check_thesis_break(position, today)` returning "flag_overdue", "close", or None
    - Flag overdue: set thesis_status="review_overdue", overdue_since=today
    - Close condition: review_overdue + negative P&L + overdue > 5 days → close with exit_reason="thesis_break_auto"
    - Log thesis-break closures with original thesis summary
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.3 Implement sigma event detection in monitor loop
    - Import `detect_sigma_event` and `compute_trailing_stddev` from sigma_detector
    - For each active position with ≥ 20 days of price_history, check for sigma events
    - Log sigma events to alerts.json with category="sigma_event", ticker, magnitude, threshold
    - Trigger immediate stop-loss and take-profit evaluation on sigma event positions
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 5.4 Integrate enhanced stop-loss with slippage-adjusted exits
    - Modify `auto_close_stopped_positions` to use `compute_fill_price` for exit prices
    - Update trade journal entries with exit_reason="stop_loss_auto" and realized_pnl_pct
    - Append critical alert to alerts.json with ticker, exit_price, loss amount
    - Restore cash_pct by 2 × size_pct_nav on close
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.5 Write property tests for take-profit and trail stop
    - **Property 6: Take-profit trim halves position and sets trail stop**
    - **Property 7: Trail stop closure fully exits the remainder**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [x] 5.6 Write property tests for thesis-break and stop-loss
    - **Property 9: Thesis-break closure requires both conditions**
    - **Property 5: Stop-loss closure restores cash and records exit**
    - **Validates: Requirements 5.1, 5.2, 5.3, 3.1, 3.2, 3.3**

- [x] 6. Checkpoint — Pipeline and monitor logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Modify `serve.py` for read-only mode
  - [x] 7.1 Disable write endpoints with HTTP 403
    - Replace `/api/accept/<order_id>` POST handler to return 403 with `{"error": "autonomous_mode_active", "message": "Manual trade approval is disabled in autonomous mode"}`
    - Replace `/api/deny/<order_id>` POST handler to return 403 with same format
    - Replace `/api/close/<ticker>` POST handler to return 403 with same format
    - Verify all GET endpoints (/api/book, /api/history, /api/pending, /api/alerts, /api/factors, /api/mark) remain unchanged
    - _Requirements: 8.3, 8.5_

  - [x] 7.2 Write property test for read-only API enforcement
    - **Property 11: Read-only API enforcement**
    - All POST to /api/accept, /api/deny → 403; all GETs → 200
    - **Validates: Requirements 8.3, 8.5**

- [x] 8. Modify `dashboard.py` for autonomous mode UI
  - [x] 8.1 Update dashboard HTML for autonomous mode
    - Remove approve/deny action buttons from pending orders display
    - Remove or disable manual close button from active positions
    - Add persistent banner: "Autonomous Mode — All pipeline-cleared trades are auto-booked"
    - Add circuit breaker state indicator (active/inactive with drawdown %)
    - Add "autonomous mode" label where manual controls were
    - _Requirements: 8.1, 8.2, 8.4, 2.3_

- [x] 9. Create launchd scheduler plists
  - [x] 9.1 Create pipeline slot plists
    - Create `plists/com.agentic-trader.pipeline-0940.plist` (9:40 AM ET)
    - Create `plists/com.agentic-trader.pipeline-1130.plist` (11:30 AM ET)
    - Create `plists/com.agentic-trader.pipeline-1330.plist` (1:30 PM ET)
    - Create `plists/com.agentic-trader.pipeline-1530.plist` (3:30 PM ET)
    - All use .venv/bin/python3 to run run_cycle.py with WorkingDirectory set
    - Configure StandardOutPath/StandardErrorPath to memos/logs/
    - _Requirements: 7.1, 7.3, 7.4_

  - [x] 9.2 Create monitor and session reset plists
    - Create `plists/com.agentic-trader.monitor.plist` with StartInterval=300 (every 5 min)
    - Create `plists/com.agentic-trader.session-reset.plist` with StartCalendarInterval at 9:30 AM
    - Session reset calls `reset_session_nav()` to snapshot book NAV for circuit breaker
    - _Requirements: 7.2, 7.4, 2.4_

  - [x] 9.3 Write property test for overlap guard
    - **Property 12: Pipeline overlap guard ensures mutual exclusion**
    - At most one concurrent pipeline execution; second is skipped
    - **Validates: Requirements 7.5**

- [x] 10. Final checkpoint — Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses Python with pytest and hypothesis (`.hypothesis/` directory present in workspace root)
- All new modules go under `src/trading/` — create `__init__.py` for the package
- Launchd plists go in a `plists/` directory at project root for version control; user installs to ~/Library/LaunchAgents/

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"] },
    { "id": 2, "tasks": ["4.1", "5.1", "5.2", "5.3", "5.4", "7.1", "8.1", "9.1", "9.2"] },
    { "id": 3, "tasks": ["4.2", "4.3", "5.5", "5.6", "7.2", "9.3"] }
  ]
}
```
