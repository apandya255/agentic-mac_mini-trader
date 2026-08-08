# Requirements Document

## Introduction

This specification defines the complete autonomous heartbeat system for the Agentic Trading Research Mac Mini. It transforms the system from a manually-invoked workflow into a fully autonomous trading desk that monitors positions intraday, enforces trail stop discipline, delivers scheduled reports and briefs via Telegram, auto-executes paper stop-loss cuts, surfaces recommendations to the dashboard, and runs the full agent pipeline on a defined cadence — all without human intervention. The principal is informed of every action, never asked to confirm one.

## Glossary

- **Heartbeat**: The autonomous scheduling and monitoring layer that drives all timed events on the Mac Mini.
- **Price_Poller**: A background process that fetches live prices from yfinance every 5 minutes during market hours and marks the book.
- **PriceService**: The existing `src/data_platform/prices.py` class that interfaces with yfinance and the SQLite database.
- **Scheduler**: The macOS `launchd`-based scheduling layer that triggers scripts at defined times, persists across reboots.
- **Agent_Pipeline**: The full orchestration script (`run_cycle.py`) that runs fundamental analysis, debate, technical scoring, risk gate, and PM recommendation phases.
- **Dashboard_Server**: The Flask application (`serve.py`) that serves the portfolio dashboard and exposes API endpoints.
- **Book**: The JSON state file (`memos/state/book.json`) containing active positions, NAV, and trade journal — the machine-readable mirror of `desk/positions.md`.
- **Positions_File**: `desk/positions.md` — the single source of truth for the paper book.
- **Pending_Orders**: Trade recommendations output by the Agent_Pipeline that await PM review via the dashboard UI.
- **Market_Hours**: US equity market regular trading hours, 09:30–16:00 ET, Monday through Friday (excluding US market holidays).
- **FX_Hours**: Continuous FX session, Sunday 17:00 ET through Friday 17:00 ET.
- **Peak**: The best level (ratio/spot/rate/price) a position has reached in its favor since entry. The trail anchors to it.
- **Trail_Breach**: When a position's combined P&L falls 2.5% from its Peak — triggers automatic paper execution of the exit.
- **Target_Touch**: When a position's P&L reaches +5% — triggers PM review, never auto-exit.
- **Two_Sigma_Interrupt**: When any position or hedge leg moves ≥ 2× its 90-day trailing standard deviation in a single day.
- **Telegram_Bot**: The notification delivery channel for all alerts, reports, and book actions.
- **Full_Desk_Run**: A complete Agent_Pipeline cycle covering all 11 fundamental sectors and 6 macro regions, run Saturdays.
- **Daily_Sweep**: A weekday Agent_Pipeline cycle focused on sectors with open positions plus the same-day earnings calendar.
- **Coverage_Digest**: The daily 17:30 ET macro + fundamental sweep summary.
- **Quiet_Hours**: 22:00–07:00 ET — only trail breaches, 2σ interrupts, Asia note, and morning brief fire during this window.
- **Watchlist**: The set of tickers in the POC_TICKERS universe defined in `run_cycle.py`.
- **NAV**: Net Asset Value of the paper book ($650,000,000 paper).
- **Flip_Condition**: The stated condition under which a thesis would be invalidated, defined at position entry.

## Requirements

### Requirement 1: Intraday Price Polling and Position Marking

**User Story:** As a portfolio manager, I want positions marked to market every 5 minutes during trading hours, so that the book always reflects near-real-time P&L and risk levels.

#### Acceptance Criteria

1. WHILE Market_Hours are active, THE Price_Poller SHALL fetch prices from yfinance for all tickers in open positions (including hedge legs) plus SPY, RSP, EFA, EEM, USO, and GLD at an interval of POLL_INTERVAL_MINUTES (default 5).
2. WHEN the Price_Poller fetches new prices, THE PriceService SHALL write them into `data/prices.db` using the existing `update()` method.
3. WHEN the Price_Poller completes a fetch cycle, THE Price_Poller SHALL update each position's P&L in `book.json` and `desk/positions.md` using carry-adjusted marking.
4. WHEN the Price_Poller marks a position, THE Price_Poller SHALL update the Peak field if the position has reached a new best level in its favor (ratio/spot/rate/price per the position's instrument type).
5. WHILE FX_Hours are active, THE Price_Poller SHALL check FX leg positions continuously (Sunday 17:00 ET through Friday 17:00 ET), independent of equity market hours.
6. IF the Price_Poller encounters a yfinance request failure, THEN THE Price_Poller SHALL log the error and retry on the next scheduled interval without crashing.
7. WHEN Market_Hours end (16:00 ET), THE Price_Poller SHALL stop equity polling until the next Market_Hours session begins while continuing FX leg monitoring during FX_Hours.
8. THE Price_Poller SHALL be configurable via the environment variable POLL_INTERVAL_MINUTES.

### Requirement 2: Trail Breach Detection and Auto-Execution

**User Story:** As a portfolio manager, I want the system to automatically cut positions when the trailing stop is breached, so that downside discipline is enforced without delay.

#### Acceptance Criteria

1. WHEN a position's combined P&L falls 2.5% from its Peak, THE Price_Poller SHALL immediately execute a paper cut at the observed price at that tick.
2. WHEN a Trail_Breach is executed, THE Price_Poller SHALL log the exit with: exit level, leg fills (each leg's observed price), P&L (% and $), days held, Peak reached, and trail slippage (gap between stop level and observed fill).
3. WHEN a Trail_Breach is executed, THE Price_Poller SHALL update `book.json` to set the position status to closed and restore the cash allocation.
4. WHEN a Trail_Breach is executed, THE Price_Poller SHALL write a journal entry to `desk/journal.md` with thesis, prices, hedge, and factor deltas.
5. WHEN a Trail_Breach is executed, THE Price_Poller SHALL write a process lesson to `desk/lessons.md`.
6. WHEN a Trail_Breach is executed, THE Price_Poller SHALL sync `desk/positions.md` to reflect the closed position.
7. WHEN a Trail_Breach is executed, THE Price_Poller SHALL send an immediate Telegram alert with the instrument, fill level, P&L, and days held.
8. WHEN a Trail_Breach is executed, THE Dashboard_Server SHALL display the stop execution in the alerts feed within the next refresh cycle.
9. THE Trail_Breach detection SHALL fire during any hour (including Quiet_Hours and outside Market_Hours for FX legs).

### Requirement 3: Target Touch Detection and PM Review

**User Story:** As a portfolio manager, I want to be notified when a position hits its +5% target so I can decide to take profit or extend the runner, without the system auto-exiting.

#### Acceptance Criteria

1. WHEN a position's combined P&L reaches +5%, THE Price_Poller SHALL NOT auto-exit the position.
2. WHEN a Target_Touch occurs, THE Price_Poller SHALL surface the position for PM review on the dashboard with a prominent visual indicator.
3. WHEN a Target_Touch occurs, THE Price_Poller SHALL send a Telegram alert with the instrument, current P&L, and a prompt to take profit or extend.
4. WHEN any position is within 0.5% of its trail level, THE Price_Poller SHALL send one warning line via Telegram, limited to once per position per calendar day.

### Requirement 4: Two-Sigma Interrupt Detection

**User Story:** As a portfolio manager, I want to be immediately alerted when any position makes an outsized move, so that I can assess whether the thesis is intact.

#### Acceptance Criteria

1. WHEN any position or hedge leg moves ≥ 2× its 90-day trailing standard deviation in a single day, THE Price_Poller SHALL trigger a Two_Sigma_Interrupt.
2. WHEN a Two_Sigma_Interrupt fires, THE Price_Poller SHALL fetch headlines for the affected ticker using the Brave search tool.
3. WHEN a Two_Sigma_Interrupt fires, THE Price_Poller SHALL send a Telegram alert stating the move magnitude, the ticker, and the identified cause — or "no visible catalyst" if no material headlines are found.
4. THE Two_Sigma_Interrupt SHALL fire during any hour including Quiet_Hours.

### Requirement 5: Hourly Headline Scan

**User Story:** As a portfolio manager, I want the system to monitor news on open positions during market hours, so that material developments are routed to the correct analyst before price moves.

#### Acceptance Criteria

1. WHILE Market_Hours are active, THE Heartbeat SHALL scan headlines every hour for all tickers with open positions in the Book.
2. WHEN material news is found that has not yet moved the position's price, THE Heartbeat SHALL route the headline to the owning fundamental or macro seat for a same-day flip-condition check.
3. WHEN headlines are immaterial to the position thesis, THE Heartbeat SHALL remain silent (no alert, no log beyond the scan record).
4. THE headline scan SHALL use the Brave search API per the TOOLS.md sourcing doctrine.

### Requirement 6: Asia Open Note (21:45 ET Sun–Thu)

**User Story:** As a portfolio manager, I want a concise Asia session preview each evening, so that I am aware of overnight developments before Asian markets open.

#### Acceptance Criteria

1. WHEN 21:45 ET arrives on Sunday through Thursday, THE Heartbeat SHALL generate an Asia open note.
2. THE Asia open note SHALL cover: Japan/Korea/Australia first session, China/HK open, USDJPY and CNH tone, US futures reaction, and anything touching book names or their ADRs.
3. THE Asia open note SHALL be limited to 8 lines or fewer.
4. WHEN the Asia open note is generated, THE Heartbeat SHALL deliver it via Telegram.
5. THE Asia open note SHALL fire during Quiet_Hours (it is exempt from the quiet-hours suppression).

### Requirement 7: Pre-Open Morning Brief (05:30 ET)

**User Story:** As a portfolio manager, I want a comprehensive pre-market briefing each morning, so that I have full context before the US session opens.

#### Acceptance Criteria

1. WHEN 05:30 ET arrives on trading days, THE Heartbeat SHALL generate a morning brief.
2. THE morning brief SHALL cover: full Asia session wrap, Europe first hours (cash, rates, EUR crosses including CEE pairs), US futures tone, prices on book tickers plus SPY/RSP/EFA/EEM/USO/GLD, headlines on book names, and today's top-3 macro releases from `desk/calendar.md`.
3. THE morning brief SHALL be limited to 12 lines or fewer.
4. WHEN the morning brief is generated, THE Heartbeat SHALL deliver it via Telegram and the outbound email mirror.
5. THE morning brief SHALL fire during Quiet_Hours (it is exempt from the quiet-hours suppression).

### Requirement 8: Post-Close Wrap (16:30 ET)

**User Story:** As a portfolio manager, I want an end-of-day summary of book performance and activity, so that I can review the day's results in one message.

#### Acceptance Criteria

1. WHEN 16:30 ET arrives on trading days, THE Heartbeat SHALL generate a post-close wrap.
2. THE post-close wrap SHALL include: book P&L (paper, carry-adjusted), today's entries and exits with fills, movers, any factor beta exceeding |0.4|, and current leverage stance.
3. THE post-close wrap SHALL be limited to 12 lines or fewer.
4. WHEN the post-close wrap is generated, THE Heartbeat SHALL deliver it via Telegram and the outbound email mirror.

### Requirement 9: Daily Coverage Digest (17:30 ET)

**User Story:** As a portfolio manager, I want a daily sweep of macro and fundamental developments across all coverage areas, so that material events are captured even outside open positions.

#### Acceptance Criteria

1. WHEN 17:30 ET arrives on trading days, THE Heartbeat SHALL trigger a daily coverage digest using the T2-tier model.
2. THE daily coverage digest macro sweep SHALL cover all 6 region/commodity mandates, reporting material items only (CB speakers and decisions, releases, politics).
3. THE daily coverage digest fundamental sweep SHALL cover only sectors with same-day earnings in universe names — results, guidance, and major headlines.
4. WHEN the coverage digest completes, THE Heartbeat SHALL write full notes to `desk/runs/YYYY-MM-DD.md`.
5. WHEN the coverage digest completes, THE Heartbeat SHALL deliver a summary of 15 lines or fewer via Telegram and the outbound email mirror.

### Requirement 10: Saturday Full Desk Run (10:00 ET)

**User Story:** As a portfolio manager, I want the complete agent pipeline to execute every Saturday morning covering all sectors and regions, so that the book is refreshed with comprehensive weekly analysis.

#### Acceptance Criteria

1. WHEN Saturday 10:00 ET arrives, THE Scheduler SHALL trigger a Full_Desk_Run of the Agent_Pipeline.
2. THE Full_Desk_Run SHALL execute the complete pipeline: all fund_* and macro_* mandates → debate → technical scoring → risk gate → PM decision per AGENTS.md.
3. WHEN the Full_Desk_Run completes, THE Agent_Pipeline SHALL write output to `desk/runs/YYYY-MM-DD.md` and approved trade recommendations to `memos/orders/`.
4. WHEN new order files are written, THE Dashboard_Server SHALL display them in the Pending Orders panel on the next API request.
5. WHEN the Full_Desk_Run generates pitches, THE Heartbeat SHALL deliver a summary plus any pitches via Telegram.
6. IF the Full_Desk_Run fails mid-execution, THEN THE Scheduler SHALL log the failure to `memos/logs/` with the phase that failed and the error message.

### Requirement 11: Weekday Daily Sweep (Automated Trade Recommendations)

**User Story:** As a portfolio manager, I want a daily filtered analysis cycle focused on my current positions, so that I receive timely updates and recommendations without waiting for the weekly run.

#### Acceptance Criteria

1. WHEN a weekday trading day arrives at the scheduled daily sweep time, THE Scheduler SHALL trigger a Daily_Sweep of the Agent_Pipeline.
2. THE Daily_Sweep SHALL run the Agent_Pipeline only for sectors that have at least one active position in the Book, plus relevant macro agents.
3. IF no active positions exist in the Book, THEN THE Daily_Sweep SHALL run a reduced set of macro agents only.
4. WHEN the Daily_Sweep completes, THE Agent_Pipeline SHALL write approved trade recommendations to `memos/orders/` in the existing order JSON format.
5. WHEN new recommendations are generated, THE Heartbeat SHALL send them via Telegram.
6. THE Daily_Sweep SHALL skip execution on US market holidays.
7. IF the Daily_Sweep fails mid-execution, THEN THE Scheduler SHALL log the failure to `memos/logs/` with the phase that failed and the error message.

### Requirement 12: Sunday Week-Ahead (18:00 ET)

**User Story:** As a portfolio manager, I want the calendar refreshed and a week-ahead summary each Sunday evening, so that I enter the week knowing the key scheduled events.

#### Acceptance Criteria

1. WHEN Sunday 18:00 ET arrives, THE Heartbeat SHALL refresh `desk/calendar.md` with: macro releases, CB meetings, earnings for book and watchlist names, and US market holidays for the coming week.
2. WHEN the calendar refresh completes, THE Heartbeat SHALL generate and deliver a week-ahead summary of 10 lines or fewer via Telegram.

### Requirement 13: Telegram Alert and Report Delivery

**User Story:** As a portfolio manager, I want all system outputs delivered to Telegram as the primary push channel, so that I receive timely notifications on my phone without checking the dashboard.

#### Acceptance Criteria

1. THE Heartbeat SHALL deliver all scheduled reports (Asia note, morning brief, post-close wrap, coverage digest, Saturday run summary, Sunday week-ahead) via Telegram.
2. WHEN a Trail_Breach cut is executed, THE Heartbeat SHALL send a Telegram alert immediately.
3. WHEN a Target_Touch occurs, THE Heartbeat SHALL send a Telegram alert immediately.
4. WHEN a Two_Sigma_Interrupt fires, THE Heartbeat SHALL send a Telegram alert immediately.
5. WHEN new trade recommendations are generated, THE Heartbeat SHALL send them via Telegram.
6. THE Telegram delivery SHALL respect the 4000-character message limit by splitting long messages into headline + detail messages, never truncating numbers.
7. THE Telegram integration SHALL use TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment configuration.
8. IF a Telegram delivery fails, THEN THE Heartbeat SHALL log the failure and retry once before marking the delivery as failed.

### Requirement 14: Dashboard Integration for Reports and Alerts

**User Story:** As a portfolio manager, I want all reports, alerts, and system activity visible on the dashboard, so that I have a single monitoring surface for the desk.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL display all scheduled reports (briefs, wraps, digests) in a Reports or Briefing section accessible from the dashboard.
2. THE Dashboard_Server SHALL display trail warnings, 2σ alerts, target touches, and stop executions in a real-time alerts feed.
3. THE Dashboard_Server SHALL display system health showing which heartbeat ticks have run today and their outcomes.
4. THE Dashboard_Server SHALL display cycle history showing all automated runs with timestamps, duration, and outcomes.
5. WHEN expected heartbeat ticks are missed (price poll gap > 10 minutes during Market_Hours, or missed scheduled report), THE Dashboard_Server SHALL display a staleness warning indicator.

### Requirement 15: Scheduling via launchd

**User Story:** As a system operator, I want each scheduled event managed by a separate launchd plist, so that the automation persists across reboots and each component can be managed independently.

#### Acceptance Criteria

1. THE Scheduler SHALL be implemented as macOS launchd plist agents installed in `~/Library/LaunchAgents/`.
2. THE Scheduler SHALL define separate plist files for each scheduled event: Price_Poller, daily sweep, full desk run, Asia note, morning brief, post-close wrap, coverage digest, Sunday week-ahead.
3. WHEN the Mac Mini reboots, THE Scheduler SHALL automatically resume all scheduled jobs without manual re-registration.
4. THE Scheduler SHALL provide an installation script (`scripts/install_scheduler.sh`) that generates and loads all plist files with correct paths.
5. THE Scheduler SHALL provide an uninstall script (`scripts/uninstall_scheduler.sh`) that unloads and removes all plist files.
6. WHILE Quiet_Hours are active (22:00–07:00 ET), THE Scheduler SHALL suppress all non-exempt events (only trail breaches, 2σ interrupts, Asia note, and morning brief fire).

### Requirement 16: Market Calendar and Holiday Awareness

**User Story:** As a system operator, I want the system to respect market holidays and session boundaries, so that resources are not wasted polling closed markets and reports are not generated on non-trading days.

#### Acceptance Criteria

1. WHEN a weekday is a US market holiday, THE Price_Poller SHALL not poll for equity prices.
2. WHEN a weekday is a US market holiday, THE Daily_Sweep SHALL skip execution.
3. THE market calendar SHALL maintain a static holiday list in code, updated annually.
4. WHILE weekends are in effect, THE Price_Poller SHALL not flag equity staleness.
5. WHILE FX_Hours are active (Sunday 17:00 ET – Friday 17:00 ET), THE Price_Poller SHALL continue monitoring FX legs regardless of equity market holidays.
6. THE market calendar module SHALL expose `is_market_open()`, `is_trading_day()`, and `is_fx_session_active()` functions.

### Requirement 17: Concurrent Execution Safety

**User Story:** As a system operator, I want to prevent data corruption when multiple automated processes access shared state simultaneously, so that the book remains consistent.

#### Acceptance Criteria

1. WHEN any process writes to `book.json`, THE process SHALL acquire an exclusive file-based advisory lock using `fcntl.flock` on a separate lock file (`book.json.lock`).
2. THE write operation SHALL use atomic writes (write to a temporary file, then `os.replace` to the target path) to prevent partial reads by concurrent readers.
3. IF a lock cannot be acquired within 30 seconds, THEN THE requesting process SHALL skip the current write cycle and log a warning.
4. THE Dashboard_Server SHALL read `book.json` without acquiring a lock (acceptable for display — worst case shows data from the previous atomic write).
5. WHEN the Agent_Pipeline is writing order files, THE Agent_Pipeline SHALL not conflict with the Price_Poller's mark-to-market updates (separate file paths, no shared lock needed for `memos/orders/`).

### Requirement 18: Logging and Observability

**User Story:** As a system operator, I want every automated cycle logged with structured data, so that I can verify the system is operating correctly and diagnose failures.

#### Acceptance Criteria

1. WHEN any automated cycle (price poll, report generation, sweep, desk run, alert dispatch) completes, THE system SHALL log a structured JSON entry to `memos/logs/` with: timestamp, cycle type, duration in seconds, outcome (success/failure/skipped), and relevant metrics.
2. THE structured log entry SHALL include: trigger source (launchd or manual), tickers updated (for price polls), proposals generated and orders written (for pipeline runs), and alert type (for interrupts).
3. WHEN the Dashboard_Server is queried at `/api/logs`, THE Dashboard_Server SHALL return all cycle logs from `memos/logs/`.
4. WHEN expected ticks are missed, THE Dashboard_Server SHALL display a staleness warning with the last successful tick time.
5. THE log directory SHALL be `memos/logs/` with file naming convention `{cycle_type}_{ISO_timestamp}.json`.

### Requirement 19: Configuration

**User Story:** As a system operator, I want all tunable parameters centralized in environment variables, so that I can adjust behavior without modifying code.

#### Acceptance Criteria

1. THE system SHALL read POLL_INTERVAL_MINUTES (default 5) from the environment to control price polling frequency.
2. THE system SHALL read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment for alert delivery.
3. THE system SHALL read OPENROUTER_API_KEY from the environment for agent pipeline LLM calls.
4. THE system SHALL maintain a static US market holiday list in code (updated annually), referenced by the market calendar module.
5. THE system SHALL read all secrets from `~/.openclaw/.env` per the TOOLS.md security model — never from workspace `.env`.

### Requirement 20: Stop-Loss Execution Record Keeping

**User Story:** As a portfolio manager, I want every auto-executed stop loss to produce a complete audit trail, so that I can review the system's discipline and measure trail slippage.

#### Acceptance Criteria

1. WHEN a Trail_Breach is auto-executed, THE system SHALL record in `desk/journal.md`: instrument, direction, entry level, exit level (observed fill), leg fills for each leg, stop level, trail slippage (observed fill minus stop level), P&L (% and $), days held, Peak reached, and timestamp.
2. WHEN a Trail_Breach is auto-executed, THE system SHALL write a process lesson to `desk/lessons.md` summarizing what worked or failed about the position.
3. WHEN a Trail_Breach is auto-executed, THE system SHALL update `desk/positions.md` to show the position as closed with exit details.
4. WHEN a Trail_Breach is auto-executed, THE system SHALL record a NAV snapshot to `memos/state/pnl_history.json`.

### Requirement 21: Scheduled CB Decision Monitoring

**User Story:** As a portfolio manager, I want to be alerted when a central bank decision in a book/watchlist currency diverges from consensus, so that I can reassess affected positions immediately.

#### Acceptance Criteria

1. WHEN a scheduled CB decision occurs for a currency with an open position or watchlist exposure (dates sourced from `desk/rates_table.md`), THE Heartbeat SHALL check the outcome versus consensus within one hour of the announcement.
2. IF the CB decision is off-consensus, THEN THE Heartbeat SHALL send a Telegram alert quantifying the surprise (actual vs. expected, basis point difference).
3. THE CB decision monitoring SHALL fire during any hour including Quiet_Hours.

### Requirement 22: Data Feed Resilience

**User Story:** As a system operator, I want the system to handle data feed outages gracefully, so that stale data is never used to mark positions or trigger stops.

#### Acceptance Criteria

1. IF the yfinance data feed is unavailable during Market_Hours, THEN THE Price_Poller SHALL send one Telegram notification and remain quiet until the feed is restored.
2. WHEN the data feed is restored, THE Price_Poller SHALL resume normal operation on the next tick without manual intervention.
3. THE Price_Poller SHALL reject quotes flagged as STALE (older than 4 hours during that instrument's market hours) and not use them for marking or stop calculations.
4. THE Price_Poller SHALL reject quotes flagged as GARBAGE (single-tick move >3% with prior tick <1 hour old, re-fetched and persisting) and not use them for marking or stop calculations.
5. WHILE the data feed is down, THE Price_Poller SHALL not trigger Trail_Breach or Target_Touch based on the last stale price.

### Requirement 23: Empty Book Behavior

**User Story:** As a system operator, I want the system to operate correctly when no positions are open, so that the monitoring and reporting infrastructure stays warm.

#### Acceptance Criteria

1. WHILE the Book contains no active positions, THE Price_Poller SHALL skip position-level checks (trail, target, 2σ) but continue fetching benchmark prices (SPY, RSP, EFA, EEM, USO, GLD).
2. WHILE the Book contains no active positions, THE morning brief and post-close wrap SHALL still run with market context only.
3. WHILE the Book contains no active positions, THE hourly headline scan SHALL be skipped.
