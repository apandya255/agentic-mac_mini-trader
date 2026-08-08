# Implementation Plan: Live Data & Automated Recommendations

## Overview

This plan implements the autonomous heartbeat system that transforms the Agentic Trading Research platform from a manually-invoked workflow into an always-on system. The implementation covers: market calendar awareness, file-locking book operations, a continuous price poller with trail/target detection, scheduled pipeline runs (daily sweep + full desk), Telegram notifications, launchd scheduling, dashboard enhancements, and structured logging. Tasks covering LLM-driven reports (Asia note, morning brief, wraps, digests, CB monitoring) are included but noted as requiring the OpenClaw/OpenRouter environment on the target Mac Mini.

## Tasks

- [x] 1. Create market calendar module and book operations core
  - [x] 1.1 Implement `src/data_platform/market_calendar.py`
    - Create `is_market_open(now=None) -> bool` checking weekday + 09:30–16:00 ET + holiday list
    - Create `is_trading_day(dt=None) -> bool` checking weekday + not holiday
    - Create `is_fx_session_active(now=None) -> bool` checking Sun 17:00 – Fri 17:00 ET
    - Create `next_market_open(now=None) -> datetime` for sleep-until logic
    - Define static `US_MARKET_HOLIDAYS` dict for 2025 and 2026
    - Use `pytz` (already available via pandas) for ET timezone handling
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [x] 1.2 Implement `src/data_platform/book_ops.py`
    - Create `LockTimeout` exception class
    - Create `book_lock(timeout=30)` context manager using `fcntl.flock` on `memos/state/book.json.lock`
    - Create `load_book() -> dict` for reading book.json
    - Create `save_book(book: dict)` with atomic write (write to `.tmp`, then `os.replace`)
    - Create `mark_positions(book: dict, price_service) -> dict` computing P&L for each active position (long/short logic, carry-adjusted)
    - Create `update_peak(position: dict, current_price: float) -> dict` tracking best level in favor
    - Create `check_trail_breach(position: dict) -> bool` detecting 2.5% fall from Peak
    - Create `check_target_touch(position: dict) -> bool` detecting +5% P&L
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 1.3, 1.4, 2.1, 3.1_

  - [x] 1.3 Write property tests for market calendar (Property 1 & 4)
    - **Property 1: Market Hours Classification** — for any datetime during regular session, `is_market_open()` returns True; outside returns False
    - **Property 4: Trading Day Holiday Check** — for any holiday/weekend `is_trading_day()` returns False; for non-holiday weekday returns True
    - Use Hypothesis with `st.datetimes()` strategy
    - **Validates: Requirements 16.1, 16.2, 16.6, 1.1, 1.5**

  - [x] 1.4 Write property tests for book operations (Property 2 & 6)
    - **Property 2: Mark-to-Market P&L Correctness** — for any entry/current price and direction, unrealized P&L computed correctly
    - **Property 6: Book Lock Serialization** — concurrent lock attempts serialize correctly; timeout raises LockTimeout
    - Use Hypothesis with `st.floats(min_value=0.01)` for prices, `st.sampled_from(["long","short"])` for direction
    - **Validates: Requirements 1.3, 17.1, 17.3**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement price poller with trail/target detection
  - [x] 3.1 Create `scripts/price_poller.py` — main loop structure
    - Implement `while True` loop gated by `is_market_open()` and `is_fx_session_active()`
    - Call `PriceService.update()` with `lookback_days=2` for position tickers + benchmarks (SPY, RSP, EFA, EEM, USO, GLD)
    - After fetch, acquire `book_lock()` and call `mark_positions()` to update book.json
    - Update Peak for each position via `update_peak()`
    - Sleep `POLL_INTERVAL_MINUTES * 60` between cycles
    - Handle `LockTimeout` gracefully (log warning, skip mark-to-market)
    - Handle yfinance failures gracefully (log error, continue next interval)
    - Exit cleanly at 16:05 ET (equity poller) while FX legs continue through FX_Hours
    - Read `POLL_INTERVAL_MINUTES` and `PRICE_POLLER_TICKERS` from environment
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 22.1, 22.2_

  - [x] 3.2 Add trail breach detection and auto-execution to price poller
    - After mark-to-market, check each position for `check_trail_breach()`
    - On breach: execute paper cut — set position status to "closed", restore cash allocation in book.json
    - Log exit with: exit level, leg fills, P&L (% and $), days held, Peak, trail slippage
    - Write journal entry to `desk/journal.md`
    - Write process lesson to `desk/lessons.md`
    - Sync `desk/positions.md` to reflect closed position
    - Queue Telegram alert (uses telegram module from task 5)
    - Trail detection runs during any hour (including Quiet_Hours, FX legs outside market hours)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 20.1, 20.2, 20.3, 20.4_

  - [x] 3.3 Add target touch detection and near-trail warning to price poller
    - After mark-to-market, check each position for `check_target_touch()`
    - On target touch: surface for PM review on dashboard (set `target_touched: true` in book.json position)
    - Do NOT auto-exit on target touch
    - Queue Telegram alert with instrument, current P&L, and prompt
    - Add near-trail warning: if position within 0.5% of trail level, send one Telegram warning per position per calendar day
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.4 Add Two-Sigma interrupt detection to price poller
    - Compute 90-day trailing standard deviation for each position and hedge leg
    - If single-day move ≥ 2× the 90d std dev, trigger Two_Sigma_Interrupt
    - Fetch headlines for affected ticker using Brave search (existing `src/data_platform/news.py`)
    - Queue Telegram alert with move magnitude, ticker, and identified cause or "no visible catalyst"
    - Fires during any hour including Quiet_Hours
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.5 Add stale/garbage quote rejection to price poller
    - Reject quotes older than 4 hours during that instrument's market hours (STALE)
    - Reject single-tick moves >3% with prior tick <1 hour old that persist on re-fetch (GARBAGE)
    - Do not mark positions or trigger trail/target based on stale prices
    - Send one Telegram notification on data feed outage, remain quiet until restored
    - _Requirements: 22.3, 22.4, 22.5_

  - [x] 3.6 Write property test for staleness detection (Property 5)
    - **Property 5: Staleness Detection** — `_stale` flag is True iff elapsed time > POLL_INTERVAL_MINUTES + 0.5 during market hours; False outside market hours
    - Use Hypothesis with `st.datetimes()` for timestamps, `st.integers(1,60)` for interval
    - **Validates: Requirements 14.5, 18.4**

- [x] 4. Checkpoint - Ensure price poller tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Telegram bot and notification delivery
  - [x] 5.1 Create `src/telegram_bot.py`
    - Read `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from environment
    - Implement `send_message(text: str)` using Telegram Bot API `sendMessage` endpoint
    - Handle 4000-char message limit by splitting into headline + detail messages (never truncate numbers)
    - Implement retry-once on delivery failure before marking as failed
    - Log all delivery attempts (success/failure) to structured logs
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

  - [x] 5.2 Write unit tests for Telegram bot
    - Test message splitting at 4000-char boundary
    - Test retry logic on simulated failure
    - Test env var configuration loading
    - _Requirements: 13.6, 13.8_

- [x] 6. Implement daily sweep and full desk run scripts
  - [x] 6.1 Modify `run_cycle.py` to add `--agents` filter flag
    - Add `--agents` argparse argument (comma-separated agent IDs)
    - In `phase_2_blind_proposals()`, filter `agents` dict to only requested IDs when flag is provided
    - Backwards-compatible: no `--agents` flag runs all agents as before
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 6.2 Create `scripts/daily_sweep.py`
    - Check `is_trading_day()` — skip and log if holiday
    - Read book.json to find active position tickers
    - Map tickers to sectors and then to `fund_*` agent IDs + relevant `macro_*` agents
    - If no active positions, run macro_northamerica, macro_westerneurope, macro_asia only
    - Invoke `run_cycle.py --agents <filtered_list>`
    - Log structured cycle entry on completion or failure
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.6, 11.7_

  - [x] 6.3 Create `scripts/full_desk_run.py`
    - Invoke `run_cycle.py` with no agent filter (all fund_* and macro_* agents)
    - Wrap execution with structured logging (start time, duration, success/failure)
    - Capture stderr on failure and write to `memos/logs/`
    - _Requirements: 10.1, 10.2, 10.3, 10.6_

  - [x] 6.4 Write property test for daily sweep agent selection (Property 3)
    - **Property 3: Daily Sweep Agent Selection** — for any book with active positions, filter includes exactly the fund_* agents for those sectors + relevant macro agents. Empty book → reduced macro set only
    - Use Hypothesis with `st.lists(st.sampled_from(SECTOR_TICKERS))` for tickers
    - **Validates: Requirements 11.2, 11.3**

- [x] 7. Checkpoint - Ensure sweep and desk run work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement launchd scheduling and install/uninstall scripts
  - [x] 8.1 Create `scripts/install_scheduler.sh`
    - Auto-detect `PROJECT_DIR` and `PYTHON_PATH`
    - Generate plist files for: price poller (weekday 09:25 ET start), daily sweep (weekday 06:00 ET), full desk run (Saturday 10:00 ET)
    - Template plist XML with correct paths, working directory, and log paths
    - Create `memos/logs/` directory if it doesn't exist
    - Load all plists with `launchctl load`
    - Make script executable
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 8.2 Create `scripts/uninstall_scheduler.sh`
    - Unload all three plists with `launchctl unload`
    - Remove plist files from `~/Library/LaunchAgents/`
    - Log each removal
    - Make script executable
    - _Requirements: 15.5_

- [x] 9. Dashboard enhancements — stale data warning and alerts
  - [x] 9.1 Add stale-data indicator to `serve.py` API
    - In `/api/book` endpoint: read `last_marked` from book.json
    - If `is_market_open()` and age > POLL_INTERVAL_MINUTES + 0.5 minutes, set `_stale: true`
    - Return `_last_poll_age_minutes` for display
    - Outside market hours: always `_stale: false`
    - _Requirements: 14.5, 18.4_

  - [x] 9.2 Add stale-data warning banner to `dashboard.html`
    - Read `_stale` flag from `/api/book` response
    - Display yellow warning banner when `_stale` is true showing elapsed minutes
    - Hide banner when data is fresh or outside market hours
    - _Requirements: 14.5_

  - [x] 9.3 Add alerts feed to dashboard
    - Create `/api/alerts` endpoint in `serve.py` reading from structured logs (trail breaches, target touches, 2σ interrupts)
    - Display alerts in a real-time feed panel on dashboard
    - Show system health: which heartbeat ticks ran today and their outcomes
    - _Requirements: 14.2, 14.3, 14.4_

  - [x] 9.4 Add `/api/logs` endpoint to `serve.py`
    - Return all cycle logs from `memos/logs/` sorted by timestamp descending
    - Include cycle history with timestamps, duration, and outcomes
    - _Requirements: 18.3_

- [x] 10. Implement structured logging for all automated cycles
  - [x] 10.1 Create logging utility in `src/data_platform/cycle_logger.py`
    - Implement `log_cycle(cycle_type, status, duration_seconds, metrics, error=None, trigger_source="launchd")`
    - Write JSON to `memos/logs/{cycle_type}_{ISO_timestamp}.json`
    - Schema: timestamp, cycle_type, trigger_source, status (success/failure/skipped), duration_seconds, metrics dict, error
    - Integrate into price_poller.py, daily_sweep.py, and full_desk_run.py
    - _Requirements: 18.1, 18.2, 18.5_

- [x] 11. Checkpoint - Ensure all components integrated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. LLM-driven scheduled reports (Mac Mini deployment)
  - [x] 12.1 Add hourly headline scan script (`scripts/headline_scan.py`)
    - During Market_Hours, scan headlines hourly for all open position tickers using Brave search API
    - Route material news to owning fundamental/macro seat for flip-condition check
    - Remain silent for immaterial headlines
    - Note: Requires OpenClaw/OpenRouter on target Mac Mini
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 12.2 Add Asia open note script (`scripts/asia_note.py`)
    - Trigger at 21:45 ET Sun–Thu
    - Generate 8-line-max Asia session preview (Japan/Korea/Australia, China/HK open, USDJPY, CNH, US futures, book name ADRs)
    - Deliver via Telegram
    - Fires during Quiet_Hours (exempt from suppression)
    - Note: Requires OpenClaw/OpenRouter LLM calls on target Mac Mini
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 12.3 Add morning brief script (`scripts/morning_brief.py`)
    - Trigger at 05:30 ET on trading days
    - Generate 12-line-max pre-open briefing (Asia wrap, Europe, US futures, book prices, headlines, top-3 macro releases)
    - Deliver via Telegram and email mirror
    - Fires during Quiet_Hours (exempt from suppression)
    - Note: Requires OpenClaw/OpenRouter LLM calls on target Mac Mini
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 12.4 Add post-close wrap script (`scripts/post_close_wrap.py`)
    - Trigger at 16:30 ET on trading days
    - Generate 12-line-max wrap (book P&L, today's entries/exits, movers, factor beta, leverage)
    - Deliver via Telegram and email mirror
    - Note: Requires OpenClaw/OpenRouter LLM calls on target Mac Mini
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 12.5 Add coverage digest script (`scripts/coverage_digest.py`)
    - Trigger at 17:30 ET on trading days
    - Use T2-tier model for macro sweep (6 regions) + fundamental sweep (same-day earnings sectors)
    - Write full notes to `desk/runs/YYYY-MM-DD.md`
    - Deliver 15-line summary via Telegram and email mirror
    - Note: Requires OpenClaw/OpenRouter LLM calls on target Mac Mini
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 12.6 Add Sunday week-ahead script (`scripts/week_ahead.py`)
    - Trigger at Sunday 18:00 ET
    - Refresh `desk/calendar.md` with macro releases, CB meetings, earnings, holidays
    - Deliver 10-line week-ahead summary via Telegram
    - Note: Requires OpenClaw/OpenRouter LLM calls on target Mac Mini
    - _Requirements: 12.1, 12.2_

  - [x] 12.7 Add CB decision monitoring to price poller
    - Within one hour of scheduled CB decision (dates from `desk/rates_table.md`), check outcome vs consensus
    - If off-consensus, send Telegram alert with actual vs expected and basis-point difference
    - Fires during any hour including Quiet_Hours
    - Note: Requires Brave search + LLM interpretation on target Mac Mini
    - _Requirements: 21.1, 21.2, 21.3_

  - [x] 12.8 Update `scripts/install_scheduler.sh` to include all scheduled report plists
    - Add plist entries for: headline scan (hourly during Market_Hours), Asia note (21:45 Sun-Thu), morning brief (05:30 weekdays), post-close wrap (16:30 weekdays), coverage digest (17:30 weekdays), week-ahead (Sunday 18:00)
    - Add Quiet_Hours suppression logic (22:00–07:00 ET) for non-exempt events
    - _Requirements: 15.2, 15.6_

- [x] 13. Wire empty-book behavior and configuration
  - [x] 13.1 Add empty-book guards throughout the system
    - Price poller: skip trail/target/2σ checks when no active positions; continue benchmark polling
    - Morning brief and post-close wrap: still run with market context only when book is empty
    - Hourly headline scan: skip entirely when book is empty
    - _Requirements: 23.1, 23.2, 23.3_

  - [x] 13.2 Verify all configuration reads from environment
    - Confirm POLL_INTERVAL_MINUTES (default 5) used everywhere
    - Confirm TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID read from env
    - Confirm OPENROUTER_API_KEY read from env for pipeline
    - Confirm secrets sourced from `~/.openclaw/.env` per TOOLS.md security model
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 14. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Tasks in group 12 (LLM-driven reports) require the OpenClaw/OpenRouter environment on the target Mac Mini — they can be implemented locally as scripts but will only be testable on the deployed machine
- The design uses Python throughout; all implementations follow existing project conventions (pathlib, subprocess, argparse)
- `pytz` is already available via the pandas dependency
- The existing `src/data_platform/prices.py` PriceService is reused for all data fetching
- File paths use the project's established conventions (`memos/state/`, `memos/logs/`, `desk/`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "5.1", "10.1"] },
    { "id": 2, "tasks": ["3.1", "5.2", "6.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "6.2", "6.3"] },
    { "id": 4, "tasks": ["3.6", "6.4", "9.1", "9.4"] },
    { "id": 5, "tasks": ["8.1", "8.2", "9.2", "9.3"] },
    { "id": 6, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7"] },
    { "id": 7, "tasks": ["12.8", "13.1", "13.2"] }
  ]
}
```
