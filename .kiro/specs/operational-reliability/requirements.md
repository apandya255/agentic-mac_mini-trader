# Requirements Document

## Introduction

This document specifies requirements for a comprehensive operational reliability and risk management system for the Agentic Trading platform. The platform runs autonomously on a Mac Mini via launchd-scheduled tasks, fetching prices via yfinance, generating and executing trade proposals through AI agent pipelines, and monitoring 5 active positions. The system must operate unattended during market hours with graceful degradation, alerting, and automatic enforcement of risk controls.

## Glossary

- **Price_Service**: The `PriceService` class responsible for fetching, storing, and querying EOD/intraday price data from yfinance and fallback sources via a local SQLite database.
- **Pipeline**: The `run_cycle.py` orchestrator that executes one full trading cycle (data refresh, proposal generation, debate, risk gate, PM decision, book update).
- **Monitor**: The `monitor.py` risk and alert system that enforces stop-loss, drawdown, factor beta, correlation, and holding period rules.
- **Price_Poller**: The `price_poller.py` long-running process that fetches live prices during market hours and marks positions to market.
- **Circuit_Breaker**: The module that tracks session-open NAV and blocks new trade entries when intraday drawdown exceeds -2%.
- **Overlap_Guard**: The `pipeline_lock()` context manager that prevents concurrent pipeline executions via an exclusive file lock.
- **Telegram_Notifier**: The `telegram_bot.py` module that delivers alert messages to a Telegram chat with retry-once semantics and structured logging.
- **Market_Calendar**: The module determining US equity market hours, holidays, FX session boundaries, and next-open times.
- **Book**: The `book.json` file containing all positions, NAV, session state, and portfolio metadata.
- **Trail_Stop**: A trailing stop-loss that ratchets upward from the position's peak price, closing the position when price retraces a configured percentage from peak.
- **Thesis_Review**: A scheduled date by which a position's investment thesis must be re-evaluated or the position is flagged overdue.
- **Factor_Beta**: The regression coefficient of a position's daily returns against a factor series over a 12-month window.
- **Backfill**: The process of fetching and storing historical daily price data from a position's entry date through today.
- **Session_Open_NAV**: The portfolio NAV recorded at market open (9:30 AM ET) used as the baseline for intraday drawdown calculation.
- **Alpha_Vantage**: A secondary price data provider used as a fallback when yfinance fails, accessed via the ALPHAVANTAGE_API_KEY environment variable.
- **Launchd**: The macOS system daemon that schedules and launches pipeline cycles, price polling, and monitoring at configured intervals.

## Requirements

### Requirement 1: Price Data Retry and Backoff

**User Story:** As a system operator, I want the price fetching layer to retry on transient failures with exponential backoff, so that temporary yfinance outages do not halt the trading pipeline.

#### Acceptance Criteria

1. WHEN a yfinance fetch call raises an exception (including YFTzMissingError), THE Price_Service SHALL retry the fetch up to 3 times with exponential backoff delays of 2, 4, and 8 seconds.
2. IF all 3 retries fail for a given ticker, THEN THE Price_Service SHALL log the failure with ticker, error type, and timestamp, and mark that ticker as "fetch_failed" in the cycle state.
3. WHEN a ticker is marked "fetch_failed", THE Price_Service SHALL not use stale cached data older than 4 hours during market hours as a substitute price.

### Requirement 2: Fallback Price Source

**User Story:** As a system operator, I want an Alpha Vantage fallback when yfinance is unavailable, so that price data remains accessible even during yfinance outages.

#### Acceptance Criteria

1. WHEN a yfinance fetch fails after exhausting retries AND the ALPHAVANTAGE_API_KEY environment variable is set, THE Price_Service SHALL attempt one fetch from Alpha Vantage for the failed ticker.
2. WHEN a price is sourced from Alpha Vantage, THE Price_Service SHALL tag the data with source="alpha_vantage" in the stored record.
3. IF the Alpha Vantage fetch also fails, THEN THE Price_Service SHALL mark the ticker as "unfetchable" and emit a critical alert via the Telegram_Notifier.
4. THE Price_Service SHALL limit Alpha Vantage API calls to a maximum of 5 per minute to respect free-tier rate limits.

### Requirement 3: Weekend and Holiday Price Handling

**User Story:** As a system operator, I want the system to suppress false staleness alerts on non-trading days, so that weekends and holidays do not generate spurious notifications.

#### Acceptance Criteria

1. WHILE the Market_Calendar reports that the US equity market is closed (weekend or holiday), THE Price_Poller SHALL not flag equity tickers as STALE regardless of quote age.
2. WHILE the Market_Calendar reports that the FX session is inactive (Saturday, or Sunday before 17:00 ET), THE Price_Poller SHALL not flag FX tickers as STALE.
3. WHEN the Price_Poller starts on a non-trading day, THE Price_Poller SHALL log "market_closed: skipping equity poll" and exit cleanly with code 0.

### Requirement 4: Scheduled Pipeline Verification

**User Story:** As a system operator, I want to verify that all launchd plists are correctly installed and running, so that the pipeline executes reliably at scheduled times.

#### Acceptance Criteria

1. WHEN the `install_scheduler.sh` script is executed, THE Scheduler_Installer SHALL install all 6 launchd plists (4 pipeline cycles at 09:40/11:30/13:30/15:30 ET, 1 monitor every 300 seconds, 1 session-reset).
2. WHEN a launchd job fails to load, THE Scheduler_Installer SHALL report the specific plist label and macOS error to stderr and exit with code 1.
3. THE Pipeline SHALL execute within the Overlap_Guard context, acquiring an exclusive file lock before any cycle logic runs.
4. IF the Overlap_Guard cannot acquire the lock, THEN THE Pipeline SHALL log "cycle_skipped_overlap" with the PID of the holding process and exit cleanly with code 0.

### Requirement 5: Session-Open NAV Reset

**User Story:** As a system operator, I want the session-open NAV to reset automatically at market open, so that the circuit breaker uses the correct daily baseline.

#### Acceptance Criteria

1. WHEN the Market_Calendar indicates market open (9:30 AM ET on a trading day), THE Circuit_Breaker SHALL record the current NAV from Book as the Session_Open_NAV.
2. IF the Book file is unavailable or contains invalid JSON at reset time, THEN THE Circuit_Breaker SHALL send a critical alert via Telegram_Notifier and retain the previous Session_Open_NAV.
3. THE session-reset launchd plist SHALL trigger the NAV reset at 9:30 AM ET on weekdays only.

### Requirement 6: Pipeline Failure Recovery

**User Story:** As a system operator, I want the pipeline to recover gracefully from mid-execution failures, so that a crash in one cycle does not corrupt state or prevent subsequent cycles.

#### Acceptance Criteria

1. IF the Pipeline raises an unhandled exception during execution, THEN THE Pipeline SHALL catch the exception at the top level, log the full traceback to `memos/logs/`, and exit with code 1.
2. IF the Pipeline fails mid-execution, THEN THE Pipeline SHALL not write partial results to Book (atomic write pattern: write to temp file, then rename).
3. WHEN the Pipeline exits with a non-zero code, THE Pipeline SHALL send a failure summary (cycle time, phase that failed, error message) via Telegram_Notifier.
4. THE Overlap_Guard lock SHALL be released on Pipeline exit regardless of success or failure (guaranteed via context manager finally block).

### Requirement 7: Trail Stop Computation

**User Story:** As a system operator, I want trailing stops to activate automatically after a position becomes profitable, so that gains are protected without manual intervention.

#### Acceptance Criteria

1. WHEN a position's unrealized P&L exceeds 0% for the first time after entry, THE Monitor SHALL compute and set the Trail_Stop level based on the position's configured stop_loss_method.
2. WHEN the position's peak price increases, THE Monitor SHALL ratchet the Trail_Stop upward (for long positions) or downward (for short positions) by recomputing from the new peak.
3. THE Monitor SHALL not lower a Trail_Stop for a long position or raise a Trail_Stop for a short position (monotonic ratchet).
4. WHEN a position's stop_loss_method specifies "2.5% trailing from peak", THE Monitor SHALL set the Trail_Stop at peak_price * (1 - 0.025) for long positions.

### Requirement 8: Hard Stop Enforcement

**User Story:** As a system operator, I want hard stops to execute automatically and immediately, so that losing positions are closed before losses exceed the defined threshold.

#### Acceptance Criteria

1. WHEN the current price breaches a position's stop_loss level, THE Monitor SHALL transition the position to "fully_exited" using the position state machine.
2. WHEN a position is auto-closed via stop breach, THE Monitor SHALL log the close to the trade journal with reason "stop_breach", fill price (computed via slippage model), and realized P&L.
3. WHEN a position is auto-closed, THE Monitor SHALL send a critical alert via Telegram_Notifier containing the ticker, stop level, breach price, and realized P&L.
4. IF the Price_Service cannot provide a fresh price for the position (ticker marked "fetch_failed"), THEN THE Monitor SHALL not execute the stop and SHALL send a warning alert indicating price data is unavailable for stop evaluation.

### Requirement 9: Thesis Review Enforcement

**User Story:** As a system operator, I want overdue thesis reviews to be surfaced automatically, so that stale positions are flagged for human attention.

#### Acceptance Criteria

1. WHEN the current date exceeds a position's review_date AND the position's thesis_status is not "reviewed", THE Monitor SHALL set thesis_status to "review_overdue".
2. WHEN a position's thesis_status transitions to "review_overdue", THE Monitor SHALL send a warning alert via Telegram_Notifier containing the ticker, original review_date, and days overdue.
3. WHILE a position has thesis_status "review_overdue", THE Monitor SHALL include the position in the "overdue reviews" section of every monitoring report until thesis_status is manually updated.

### Requirement 10: Factor Beta Computation

**User Story:** As a system operator, I want factor betas computed and monitored for each position, so that concentrated factor exposures are detected before they breach limits.

#### Acceptance Criteria

1. THE Monitor SHALL compute factor betas for each active position by running a 12-month (252 trading day) daily-return regression against each configured factor series.
2. THE Monitor SHALL store computed factor betas in `memos/state/factors.json` with the computation date and position ticker as keys.
3. WHEN a position's absolute factor beta exceeds 0.4, THE Monitor SHALL emit a warning alert indicating the factor name, beta value, and the 0.6 breach threshold.
4. WHEN a position's absolute factor beta exceeds 0.6, THE Monitor SHALL emit a critical alert and recommend position reduction.
5. IF insufficient price history exists (fewer than 126 trading days), THEN THE Monitor SHALL skip beta computation for that position and log "insufficient_history" with the available day count.

### Requirement 11: Price History Backfill

**User Story:** As a system operator, I want complete price history from each position's entry date, so that equity curves, volatility, and drawdown metrics are accurate.

#### Acceptance Criteria

1. WHEN the Mark_to_Market process runs, THE Price_Service SHALL verify that each active position has continuous daily price data from entry_date through today.
2. IF gaps exist in a position's price history, THEN THE Price_Service SHALL fetch missing data from yfinance (or Alpha Vantage as fallback) for the gap period.
3. WHEN backfill completes for a position, THE Price_Service SHALL log the ticker, number of days backfilled, and any remaining gaps.
4. THE Price_Service SHALL not attempt backfill for dates that fall on weekends or market holidays as determined by Market_Calendar.

### Requirement 12: System Service Resilience

**User Story:** As a system operator, I want critical services (dashboard server, Cloudflare tunnel) to restart automatically after a reboot, so that the platform recovers without manual intervention.

#### Acceptance Criteria

1. THE serve.py launchd plist SHALL have RunAtLoad set to true, causing the Flask dashboard to start automatically when the user logs in.
2. THE Cloudflare tunnel launchd plist SHALL have RunAtLoad set to true and KeepAlive set to true, restarting the tunnel if it crashes.
3. IF the serve.py process exits unexpectedly, THEN THE Launchd configuration SHALL restart the process after a 10-second delay (ThrottleInterval).
4. WHEN a service restarts after failure, THE system SHALL log the restart event with timestamp and previous exit code to `memos/logs/service_restarts.log`.

### Requirement 13: Telegram Alert Delivery Pipeline

**User Story:** As a system operator, I want reliable Telegram delivery for critical alerts, so that stop breaches, circuit breaker activations, and pipeline failures reach me immediately.

#### Acceptance Criteria

1. WHEN a critical alert is generated (stop breach, circuit breaker activation, pipeline failure, unfetchable ticker), THE Telegram_Notifier SHALL deliver the message within 30 seconds of generation.
2. IF the first Telegram delivery attempt fails, THEN THE Telegram_Notifier SHALL retry once after a 1-second delay before marking the delivery as failed.
3. WHEN a Telegram delivery fails after retry, THE Telegram_Notifier SHALL write the undelivered message to `memos/logs/undelivered_alerts.json` for later manual review.
4. THE Telegram_Notifier SHALL prefix critical alerts with "CRITICAL:", warning alerts with "WARNING:", and informational alerts with "INFO:" for visual severity distinction.

### Requirement 14: Pipeline Execution Logging

**User Story:** As a system operator, I want structured logging for every pipeline cycle, so that I can audit execution history and diagnose failures.

#### Acceptance Criteria

1. WHEN the Pipeline starts a cycle, THE Pipeline SHALL log a structured entry containing cycle_id (ISO timestamp), trigger_source (launchd or manual), and phase ("start").
2. WHEN each pipeline phase completes, THE Pipeline SHALL log the phase name, duration in seconds, and outcome (success/failure/skipped).
3. WHEN the Pipeline completes a full cycle, THE Pipeline SHALL log the total duration, number of proposals generated, number of trades booked, and final exit code.
4. THE Pipeline SHALL write all structured logs to `memos/logs/` as individual JSON files with naming pattern `cycle_{timestamp}.json`.

### Requirement 15: Drawdown Monitoring and Progressive Deleverage

**User Story:** As a system operator, I want progressive deleverage recommendations at increasing drawdown thresholds, so that the portfolio has a structured response to deteriorating conditions.

#### Acceptance Criteria

1. WHEN portfolio drawdown reaches -2% from Session_Open_NAV, THE Circuit_Breaker SHALL activate and block new trade entries.
2. WHEN portfolio drawdown reaches -3% from Session_Open_NAV, THE Monitor SHALL emit a critical alert recommending deleverage of the most-losing position.
3. WHEN portfolio drawdown reaches -4% from Session_Open_NAV, THE Monitor SHALL emit an emergency alert recommending closing all positions and SHALL log an "emergency_deleverage" event.
4. THE Monitor SHALL compute portfolio drawdown using only positions with fresh (non-stale) prices, excluding positions marked "fetch_failed" from the NAV calculation.
