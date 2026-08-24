# Requirements Document

## Introduction

The Autonomous Trading Loop removes human approval from the trading pipeline and converts the system to a fully autonomous paper-trading operation. The pipeline currently generates trade proposals through agent debate, risk gating, and PM sizing — then holds orders as "pending" for human accept/deny on the dashboard. This feature auto-books all trades that clear the pipeline gates, adds automated exit logic (stop-loss close, take-profit trim, thesis-break close), introduces a circuit breaker on intraday drawdown, schedules the pipeline at fixed intraday slots plus event-triggered runs, and makes the dashboard read-only.

## Glossary

- **Pipeline**: The 8-phase trade generation cycle implemented in `run_cycle.py` (data refresh → proposals → debate → conviction → technical scoring → risk gate → PM decision → book update).
- **Book**: The JSON state file (`memos/state/book.json`) containing NAV, positions, cash percentage, and trade journal.
- **Circuit_Breaker**: A safety mechanism that pauses new trade entries when intraday portfolio drawdown reaches a defined threshold.
- **Position_Monitor**: The continuous monitoring process (`monitor.py`) that evaluates active positions for stop-loss breaches, take-profit targets, and anomalous moves.
- **Scheduler**: The launchd plist-based scheduling system that triggers pipeline runs and position monitor cycles at defined times.
- **Dashboard**: The Flask web application (`serve.py`) and its HTML frontend that displays portfolio state, positions, and trade history.
- **Auto_Booker**: The logic in Phase 8 of the pipeline that automatically books orders into the book without human intervention when all gate conditions are met.
- **Slippage_Model**: The pricing adjustment applied to fill prices, using the last observed market price with a configurable slippage factor to simulate realistic paper execution.
- **Sigma_Event**: A price move of 2 or more standard deviations (computed over trailing 20-day returns) in any held position that triggers an unscheduled monitor cycle.
- **Trail_Stop**: A trailing stop-loss that adjusts upward as a position gains, locking in profits while protecting against reversals.
- **NAV**: Net Asset Value of the paper portfolio, currently $650M initial value.

## Requirements

### Requirement 1: Autonomous Order Booking

**User Story:** As a portfolio system operator, I want all trades that clear the pipeline gates to be automatically booked into the portfolio, so that the system operates without human intervention during market hours.

#### Acceptance Criteria

1. WHEN an order passes all pipeline gates (conviction ≥ 5, risk decision = "approved", PM execute = true), THE Auto_Booker SHALL add the position to the Book at the slippage-adjusted last observed price without requiring human approval.
2. WHEN the Auto_Booker books a position, THE Auto_Booker SHALL record the entry price as the last observed close price multiplied by (1 + slippage) for long entries and (1 - slippage) for short entries, where slippage defaults to 5 basis points.
3. WHEN the Auto_Booker books a position, THE Auto_Booker SHALL log the full pipeline provenance (proposal_id, debate results, tech score, risk decision, PM sizing) in the trade journal.
4. WHEN the Auto_Booker books a position, THE Auto_Booker SHALL reduce book cash_pct by the position size_pct_nav multiplied by 2 (both legs of the pair trade).

### Requirement 2: Circuit Breaker

**User Story:** As a risk manager, I want the system to pause new trade entries when the portfolio experiences excessive intraday losses, so that drawdowns do not compound during adverse conditions.

#### Acceptance Criteria

1. WHILE the portfolio intraday drawdown (current NAV minus session-open NAV divided by session-open NAV) exceeds -2%, THE Auto_Booker SHALL reject all new trade entries and log the rejection reason as "circuit_breaker_active".
2. WHEN the Circuit_Breaker activates, THE Pipeline SHALL skip Phase 8 booking for any orders generated in that cycle and persist the orders with status "circuit_breaker_held".
3. WHEN the Circuit_Breaker activates, THE Dashboard SHALL display a visible indicator showing the circuit breaker state and the current intraday drawdown percentage.
4. WHEN a new trading session begins (9:30 AM ET), THE Circuit_Breaker SHALL reset by recording the session-open NAV from the current book NAV.

### Requirement 3: Automated Stop-Loss Exit

**User Story:** As a portfolio system operator, I want positions that breach their stop-loss to be fully closed automatically, so that losses are contained without human delay.

#### Acceptance Criteria

1. WHEN a position's combined_pnl_pct breaches the stop-loss level defined in stop_loss_method, THE Position_Monitor SHALL close the position fully by setting status to "closed", recording exit_price at slippage-adjusted last observed price, and restoring cash_pct.
2. WHEN the Position_Monitor closes a stop-loss position, THE Position_Monitor SHALL log the closure in the trade journal with exit_reason = "stop_loss_auto" and the realized P&L percentage.
3. WHEN the Position_Monitor closes a stop-loss position, THE Position_Monitor SHALL send a notification (appended to alerts.json with level "critical") documenting the ticker, exit price, and loss amount.

### Requirement 4: Automated Take-Profit Management

**User Story:** As a portfolio system operator, I want positions that reach their profit target to be partially trimmed and the remainder trailed, so that profits are captured while allowing further upside.

#### Acceptance Criteria

1. WHEN a position's combined_pnl_pct reaches the take-profit level defined in the position's take_profit field, THE Position_Monitor SHALL close 50% of the position by reducing size_pct_nav by half and recording the partial exit in the trade journal.
2. WHEN the Position_Monitor executes a 50% trim, THE Position_Monitor SHALL set a Trail_Stop on the remaining position at 50% of the unrealized gain from entry (e.g., if gain is 6%, trail starts at 3% from current level).
3. WHEN the remaining trailed position's price retraces past the Trail_Stop level, THE Position_Monitor SHALL close the remainder fully and log exit_reason = "trail_stop_auto".
4. THE Position_Monitor SHALL track the trim state using a "trim_status" field on the position: "untrimmed", "half_trimmed", or "fully_exited".

### Requirement 5: Thesis-Break Exit

**User Story:** As a portfolio system operator, I want positions to be closed when the original investment thesis is invalidated, so that capital is not committed to trades whose rationale no longer holds.

#### Acceptance Criteria

1. WHEN the Position_Monitor detects a position held beyond its expected_holding_period without the target being reached, THE Position_Monitor SHALL flag the position with thesis_status = "review_overdue".
2. WHEN a position's combined_pnl_pct is negative and the position has been flagged as "review_overdue" for more than 5 trading days, THE Position_Monitor SHALL close the position fully and log exit_reason = "thesis_break_auto".
3. WHEN the Position_Monitor closes a thesis-break position, THE Position_Monitor SHALL log the closure in the trade journal with the original thesis summary and the reason for invalidation.

### Requirement 6: Sigma Event Trigger

**User Story:** As a portfolio system operator, I want the position monitor to run immediately when a held position makes an abnormally large move, so that stop-losses and take-profits are evaluated promptly.

#### Acceptance Criteria

1. WHEN any active position's daily price change exceeds 2 standard deviations of its trailing 20-day return distribution, THE Scheduler SHALL trigger an unscheduled Position_Monitor cycle within 5 minutes.
2. WHEN a Sigma_Event is detected, THE Position_Monitor SHALL log the event in alerts.json with category "sigma_event", the ticker, the magnitude of the move, and the computed 2σ threshold.
3. THE Position_Monitor SHALL compute the trailing 20-day standard deviation using the position's price_history field (daily_change_pct values for the last 20 records).

### Requirement 7: Scheduled Pipeline Execution

**User Story:** As a portfolio system operator, I want the pipeline to run automatically at fixed times during market hours, so that the system generates trade ideas without manual triggering.

#### Acceptance Criteria

1. THE Scheduler SHALL trigger a full Pipeline cycle at 9:40 AM, 11:30 AM, 1:30 PM, and 3:30 PM Eastern Time on market-open days (Monday through Friday, excluding US market holidays).
2. THE Scheduler SHALL trigger a Position_Monitor cycle every 5 minutes between 9:30 AM and 4:00 PM Eastern Time on market-open days.
3. WHEN the Scheduler triggers a Pipeline cycle, THE Pipeline SHALL execute all 8 phases sequentially including the autonomous Phase 8 booking.
4. THE Scheduler SHALL be implemented as macOS launchd plist files installed in ~/Library/LaunchAgents/ with appropriate StartCalendarInterval or StartInterval configurations.
5. IF a Pipeline cycle is already running when a scheduled trigger fires, THEN THE Scheduler SHALL skip the duplicate trigger and log a "cycle_skipped_overlap" event.

### Requirement 8: Dashboard Read-Only Mode

**User Story:** As a portfolio system operator, I want the dashboard to become read-only since trades are now auto-booked, so that accidental manual intervention cannot disrupt the autonomous loop.

#### Acceptance Criteria

1. THE Dashboard SHALL remove all approve/deny action buttons from the pending orders display.
2. THE Dashboard SHALL remove the manual close button from active positions or disable the control with a visible "autonomous mode" label.
3. WHEN a client sends a POST request to /api/accept/ or /api/deny/, THE Dashboard SHALL return HTTP 403 with a JSON body containing {"error": "autonomous_mode_active", "message": "Manual trade approval is disabled in autonomous mode"}.
4. THE Dashboard SHALL display a persistent banner indicating "Autonomous Mode — All pipeline-cleared trades are auto-booked".
5. THE Dashboard SHALL continue to serve all read endpoints (/api/book, /api/history, /api/pending, /api/alerts, /api/factors, /api/mark) without modification.

### Requirement 9: Slippage-Adjusted Fill Pricing

**User Story:** As a portfolio system operator, I want all paper fills to include a slippage adjustment, so that the paper book simulates realistic execution costs.

#### Acceptance Criteria

1. WHEN the Auto_Booker or Position_Monitor fills a trade (entry or exit), THE Slippage_Model SHALL adjust the fill price by applying a configurable slippage factor (default: 5 basis points adverse to the trade direction).
2. WHEN entering a long position, THE Slippage_Model SHALL set entry_price = last_observed_price × (1 + slippage_bps / 10000).
3. WHEN entering a short position, THE Slippage_Model SHALL set entry_price = last_observed_price × (1 - slippage_bps / 10000).
4. WHEN exiting a long position, THE Slippage_Model SHALL set exit_price = last_observed_price × (1 - slippage_bps / 10000).
5. WHEN exiting a short position, THE Slippage_Model SHALL set exit_price = last_observed_price × (1 + slippage_bps / 10000).
6. THE Slippage_Model SHALL read the slippage_bps value from an environment variable SLIPPAGE_BPS, defaulting to 5 if not set.

### Requirement 10: Pipeline Gate Validation

**User Story:** As a risk manager, I want the autonomous booking logic to enforce all three gate conditions strictly before any trade is booked, so that no trade enters the book without full pipeline clearance.

#### Acceptance Criteria

1. THE Auto_Booker SHALL verify that the order's final conviction score is greater than or equal to 5 before booking.
2. THE Auto_Booker SHALL verify that the risk gate decision field equals "approved" or "approved_with_modifications" before booking.
3. THE Auto_Booker SHALL verify that the PM decision execute field equals true before booking.
4. IF any gate condition is not met, THEN THE Auto_Booker SHALL reject the order and log it in the trade journal with action = "auto_rejected" and the specific failing gate condition.
