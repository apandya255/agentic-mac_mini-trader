# Implementation Plan: Operational Reliability

## Overview

This plan implements operational reliability enhancements across the Agentic Trading platform — covering price data resilience (retry/backoff, Alpha Vantage fallback, staleness suppression, backfill), pipeline safety (structured logging, atomic writes, failure recovery), risk monitoring (trail stop refinement, factor betas, progressive deleverage), system service resilience (launchd KeepAlive/ThrottleInterval), and alerting (Telegram severity prefixes, undelivered persistence).

Tasks are grouped into logical phases: price infrastructure first (other components depend on it), then risk monitoring, pipeline hardening, system resilience, and finally integration testing.

## Tasks

- [x] 1. Price Infrastructure — Retry, Fallback, and Calendar
  - [x] 1.1 Implement exponential backoff retry in PriceService
    - Add `_fetch_with_retry(ticker, start, max_retries=3)` method to `src/data_platform/prices.py`
    - Wrap `yf.download()` with try/except, sleeping 2^attempt seconds between retries (2, 4, 8s)
    - Return `pd.DataFrame | None` — None on full exhaustion
    - Add `fetch_status` dict tracking per-ticker outcome ("ok", "fetch_failed", "unfetchable")
    - Modify `update()` to call `_fetch_with_retry()` instead of direct `yf.download()`
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Add Alpha Vantage fallback fetcher
    - Add `_fetch_alpha_vantage(ticker, start_date)` method using stdlib `urllib` (no `requests`)
    - Parse Alpha Vantage TIME_SERIES_DAILY JSON response into a DataFrame matching yfinance schema
    - Read `ALPHAVANTAGE_API_KEY` from environment; skip fallback if not set
    - Add module-level token bucket `_av_rate_limiter` enforcing 5 calls/minute
    - Tag fetched data with `source="alpha_vantage"` for the `price_history` table
    - Wire into `update()`: call after `_fetch_with_retry()` returns None
    - If AV also fails, mark ticker "unfetchable" and send critical Telegram alert
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 1.3 Add `source` column to price_history SQLite table
    - Alter `_init_db()` to add `source TEXT DEFAULT 'yfinance'` column (migration-safe: use `ALTER TABLE ADD COLUMN` if table exists without it)
    - Update INSERT statement to include `source` parameter
    - _Requirements: 2.2_

  - [x] 1.4 Create market calendar module
    - Create `src/data_platform/market_calendar.py`
    - Implement `is_trading_day(dt: date) -> bool` checking weekends + US market holidays (hardcoded list + NYSE holiday rules)
    - Implement `is_equity_stale_check_suppressed(now: datetime | None = None) -> bool`
    - Implement `is_fx_stale_check_suppressed(now: datetime | None = None) -> bool`
    - Include `next_market_open(now: datetime) -> datetime` utility
    - _Requirements: 3.1, 3.2, 3.3, 11.4_

  - [x] 1.5 Write property tests for retry backoff and staleness suppression
    - **Property 1: Retry Backoff Timing** — For all retry counts 0-3, verify cumulative delay matches 2^i sum formula
    - **Property 4: Weekend Staleness Suppression** — For all weekend/holiday datetimes, no stale flag raised
    - **Validates: Requirements 1.1, 3.1, 3.2**

  - [x] 1.6 Implement backfill coordinator in PriceService
    - Add `backfill_position(ticker, entry_date) -> dict` method
    - Check for gaps in price_history between entry_date and today
    - Skip weekends/holidays using `market_calendar.is_trading_day()`
    - Fetch missing data via `_fetch_with_retry` then `_fetch_alpha_vantage` fallback
    - Return `{"ticker": str, "days_backfilled": int, "gaps_remaining": int}`
    - Log backfill actions
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 1.7 Write property test for Alpha Vantage rate limiting
    - **Property 3: Alpha Vantage Rate Limiting** — For all sequences of N fetch attempts within 60s, at most 5 execute
    - **Validates: Requirements 2.4**

- [x] 2. Checkpoint — Ensure all price infrastructure tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Risk Monitoring — Trail Stops, Factor Betas, Drawdown
  - [x] 3.1 Refine trail stop computation in monitor.py
    - Update `compute_trail_stop_level()` signature to accept `peak_price` instead of `current_price`, plus `method` parameter
    - Implement "2.5% trailing from peak" semantics: `trail_stop = peak_price * (1 - 0.025)` for longs
    - Add monotonic ratchet enforcement: compare new trail level with existing, keep the higher (long) or lower (short)
    - Trigger trail stop computation when P&L first exceeds 0% (add `trail_activated` flag to position)
    - Update `should_trail_stop_close()` and related callers
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 3.2 Write property test for trail stop monotonic ratchet
    - **Property 7: Trail Stop Monotonic Ratchet** — For all monotonically increasing peak sequences, trail stops never decrease (long) or increase (short)
    - **Validates: Requirements 7.2, 7.3**

  - [x] 3.3 Enhance hard stop enforcement
    - Ensure `auto_close_stopped_positions()` transitions through valid state machine paths
    - Add guard: if ticker is "fetch_failed", skip stop execution and emit WARNING alert
    - Verify exit_reason logged as "stop_breach" (currently "stop_loss_auto" — align with spec)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 3.4 Write property test for hard stop state transition validity
    - **Property 8: Hard Stop State Transition Validity** — For all stop-triggered positions, trim_status transitions through valid paths only
    - **Validates: Requirements 8.1**

  - [x] 3.5 Create factor beta computation module
    - Create `src/trading/factor_beta.py`
    - Implement `FactorBetaResult` dataclass (ticker, factor_name, beta, r_squared, trading_days_used, computed_date)
    - Implement `compute_factor_betas(ticker, price_service, factor_tickers, min_days=126)` using OLS regression (numpy-only, no sklearn)
    - Implement `load_factors()` and `save_factors()` for `memos/state/factors.json`
    - Add alert logic: |beta| > 0.4 → warning, |beta| > 0.6 → critical
    - Skip computation if fewer than 126 trading days available, log "insufficient_history"
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 3.6 Write property test for factor beta alert thresholds
    - **Property 11: Factor Beta Alert Thresholds** — For all beta values, correct alert level emitted (warning iff |beta| > 0.4, critical iff |beta| > 0.6)
    - **Validates: Requirements 10.3, 10.4**

  - [x] 3.7 Add progressive deleverage to circuit breaker
    - Add `DELEVERAGE_THRESHOLD = -0.03` and `EMERGENCY_THRESHOLD = -0.04` constants to `src/trading/circuit_breaker.py`
    - Implement `compute_progressive_deleverage(current_nav, session_open_nav) -> str | None` returning None, "deleverage", or "emergency"
    - Integrate into monitor.py `check_drawdown()` — emit correct alert level at each threshold
    - Exclude positions with "fetch_failed" prices from NAV computation
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 3.8 Write property test for drawdown progressive thresholds
    - **Property 9: Drawdown Progressive Thresholds** — For all NAV/session_open_nav pairs, exactly the correct threshold alert is emitted
    - **Validates: Requirements 15.1, 15.2, 15.3**

  - [x] 3.9 Enhance thesis review enforcement in monitor.py
    - Update `check_thesis_break()` to check `review_date` field (not just holding period) and set `thesis_status = "review_overdue"`
    - Send warning alert via Telegram with ticker, original review_date, and days overdue
    - Ensure overdue positions appear in every monitoring report until manually updated
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 3.10 Write property test for thesis review overdue detection
    - **Property 10: Thesis Review Overdue Detection** — For all active positions past review_date with thesis_status != "reviewed", monitor sets thesis_status to "review_overdue"
    - **Validates: Requirements 9.1**

- [x] 4. Checkpoint — Ensure all risk monitoring tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Pipeline Hardening — Logging, Atomic Writes, Recovery
  - [x] 5.1 Create structured cycle logger module
    - Create `src/data_platform/cycle_logger.py`
    - Implement `log_cycle_start(trigger_source) -> str` returning cycle_id (ISO timestamp)
    - Implement `log_phase_complete(cycle_id, phase, duration_s, outcome)`
    - Implement `log_cycle_complete(cycle_id, total_duration_s, proposals, trades, exit_code)`
    - Write JSON to `memos/logs/cycle_{timestamp}.json` matching the data model in design
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 5.2 Write property test for pipeline cycle logging completeness
    - **Property 13: Pipeline Cycle Logging Completeness** — For all completed cycles, log contains start entry, per-phase entries, and summary
    - **Validates: Requirements 14.1, 14.2, 14.3**

  - [x] 5.3 Integrate structured logging and atomic writes into run_cycle.py
    - Wrap pipeline execution in `pipeline_lock()` context manager (overlap guard)
    - Add top-level try/except catching all exceptions, logging traceback to `memos/logs/`
    - Replace direct `book.json` writes with atomic pattern (write to `.tmp`, then `os.replace`)
    - Call `log_cycle_start()` at beginning, `log_phase_complete()` after each phase, `log_cycle_complete()` at end
    - On failure: send Telegram alert with cycle time, failed phase, and error message
    - Exit with code 1 on failure, code 0 on success or overlap skip
    - _Requirements: 4.3, 4.4, 6.1, 6.2, 6.3, 6.4_

  - [x] 5.4 Write property test for atomic book write integrity
    - **Property 6: Atomic Book Write Integrity** — For all failure points, book.json contains either complete previous state or complete new state
    - **Validates: Requirements 6.2**

  - [x] 5.5 Write property test for overlap guard mutual exclusion
    - **Property 5: Overlap Guard Mutual Exclusion** — For two concurrent invocations, exactly one acquires lock
    - **Validates: Requirements 4.3, 4.4**

- [x] 6. Checkpoint — Ensure all pipeline hardening tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Telegram Alert Pipeline Enhancements
  - [x] 7.1 Add severity prefix and undelivered persistence to telegram_bot.py
    - Modify `send_message()` signature to accept `severity: str = "info"` parameter
    - Prefix messages with "CRITICAL:", "WARNING:", or "INFO:" based on severity
    - Add `_persist_undelivered(message, severity, error)` writing to `memos/logs/undelivered_alerts.json`
    - On delivery failure after retry, call `_persist_undelivered()` before returning False
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 7.2 Write property test for Telegram severity prefix invariant
    - **Property 12: Telegram Severity Prefix Invariant** — For all severity values, correct prefix applied to message text
    - **Validates: Requirements 13.4**

  - [x] 7.3 Update all Telegram callers to pass severity
    - Update `monitor.py` alert dispatch to pass severity="critical"/"warning"/"info" based on alert level
    - Update `run_cycle.py` failure alert to pass severity="critical"
    - Update circuit breaker alerts to pass severity="critical"
    - _Requirements: 13.1, 13.4_

- [x] 8. System Service Resilience — Launchd Plist Updates
  - [x] 8.1 Update serve.py and Cloudflare tunnel plists for auto-restart
    - Update `plists/com.agentic-trader.serve.plist` (or create if absent): set `RunAtLoad=true`, `KeepAlive=true`, `ThrottleInterval=10`
    - Update Cloudflare tunnel plist: set `RunAtLoad=true`, `KeepAlive=true`
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 8.2 Add service restart logging
    - Add a restart-logging wrapper or plist hook that appends to `memos/logs/service_restarts.log`
    - Log format: `{timestamp} {service_name} restarted (previous exit code: {code}, signal: {signal})`
    - _Requirements: 12.4_

  - [x] 8.3 Enhance session-open NAV reset with error handling
    - Modify `reset_session_nav()` in `src/trading/circuit_breaker.py` to catch `FileNotFoundError` and `json.JSONDecodeError`
    - On error: send critical Telegram alert, retain previous `session_open_nav` value (read from a sidecar state file)
    - Verify session-reset plist triggers at 9:30 AM ET on weekdays only
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 8.4 Update install_scheduler.sh for new plist features
    - Add pipeline schedule plists for all 4 intraday cycles (09:40, 11:30, 13:30, 15:30 ET)
    - Add monitor plist with `KeepAlive` and `ThrottleInterval`
    - Add session-reset plist at 09:30 ET weekdays
    - Verify all 6 plists install and load correctly
    - _Requirements: 4.1, 4.2_

- [x] 9. Integration Wiring
  - [x] 9.1 Integrate retry/fallback and staleness gating into price_poller.py
    - Update `scripts/price_poller.py` to use new `_fetch_with_retry()` path (via `PriceService.update()`)
    - Add market calendar check at start: if `is_equity_stale_check_suppressed()`, log and exit
    - Gate staleness alerts: only flag tickers as STALE when market is open and quote > 4 hours old
    - _Requirements: 1.3, 3.1, 3.2, 3.3_

  - [x] 9.2 Integrate backfill coordinator into mark_to_market.py
    - Call `price_service.backfill_position(ticker, entry_date)` for each active position during mark-to-market
    - Log backfill results
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 9.3 Integrate factor betas into monitor.py
    - Import `compute_factor_betas` from `src/trading/factor_beta.py`
    - Add `check_factor_betas(book)` function calling compute for each active position
    - Add factor beta alerts to `all_alerts` in `main()`
    - Configure factor tickers: `{"market": "SPY", "energy": "XLE", "tech": "XLK", "healthcare": "XLV"}`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 9.4 Wire progressive deleverage alerts into monitor.py main loop
    - Call `compute_progressive_deleverage()` from circuit_breaker in `check_drawdown()`
    - Emit appropriate alert at each threshold level
    - _Requirements: 15.1, 15.2, 15.3_

- [x] 10. Final Checkpoint — Full integration test pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The project already uses Hypothesis for property-based testing (`.hypothesis/` directory present)
- All new modules follow existing conventions: stdlib `urllib` for HTTP, no external dependencies beyond yfinance/numpy/pandas

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.3", "1.4"] },
    { "id": 1, "tasks": ["1.1", "1.2"] },
    { "id": 2, "tasks": ["1.5", "1.6", "1.7"] },
    { "id": 3, "tasks": ["3.1", "3.5", "3.7", "5.1", "7.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.6", "3.8", "3.9", "5.2", "7.2"] },
    { "id": 5, "tasks": ["3.4", "3.10", "5.3", "7.3", "8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["5.4", "5.5", "8.4"] },
    { "id": 7, "tasks": ["9.1", "9.2", "9.3", "9.4"] }
  ]
}
```
