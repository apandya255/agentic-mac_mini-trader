# Implementation Plan: Dashboard Autonomous Revamp

## Overview

Revamp the Jimothy Capital dashboard to surface autonomous trading mode data. Implementation modifies `dashboard.py` (HTML/CSS/JS generation) and extends `serve.py` (alerts endpoint). All client-side code is vanilla JavaScript; property tests are Python with Hypothesis.

## Tasks

- [x] 1. Extend serve.py alerts endpoint and add computation utility functions
  - [x] 1.1 Enhance `/api/alerts` endpoint in serve.py to merge monitor alerts from `memos/state/alerts.json`
    - Read existing `/api/alerts` route and add monitor_alerts loading from `ALERTS_PATH`
    - Return combined response with `alerts`, `monitor_alerts`, and `health` fields
    - Handle missing file gracefully (return empty monitor_alerts if file doesn't exist)
    - _Requirements: 3.1, 3.2_

  - [x] 1.2 Add client-side computation functions to dashboard.py JS generation
    - Add `computeGrossExposure(positions)` — sum of absolute `size_pct_nav` values
    - Add `computeNetExposure(positions)` — signed sum based on direction
    - Add `computeAveragePairPnL(positions)` — average of `combined_pnl_pct`
    - Add `computeCapitalFreedByTrims(positions, nav)` — sum of freed capital from half_trimmed positions
    - Add `computeTrailStopProximity(position)` — percentage distance from trail stop
    - Add `computeTrailing20dVol(priceHistory)` — sample stddev of last 20 daily_change_pct
    - Add `computeDrawdownFromPeak(navHistory)` — max drawdown from high-water mark
    - Add `classifyFactorBeta(beta)` — returns "green"/"amber"/"red" based on thresholds
    - Add `computeDaysOverdue(thesisStatus, lastReviewDate)` — days since last review
    - Add `computeConvictionTrajectory(debate)` — ordered conviction values across rounds
    - _Requirements: 2.2, 2.3, 1.2, 3.4, 3.6, 4.5_

  - [x] 1.3 Write property tests for computation functions (Properties 1–2: Exposure calculations)
    - **Property 1: Gross exposure is the sum of absolute position sizes**
    - **Property 2: Net exposure is the signed sum of position sizes**
    - **Validates: Requirements 2.2**
    - Implement Python equivalents of computeGrossExposure and computeNetExposure
    - Use Hypothesis to generate random position lists with varying size_pct_nav and direction

  - [x] 1.4 Write property tests for computation functions (Properties 3–5: Position metrics)
    - **Property 3: Trail stop proximity percentage is consistent with price data**
    - **Property 4: Factor beta classification respects threshold ordering**
    - **Property 5: Capital freed by trims aggregation is non-negative**
    - **Validates: Requirements 1.2, 3.4, 2.3**
    - Implement Python equivalents of computeTrailStopProximity, classifyFactorBeta, computeCapitalFreedByTrims
    - Use Hypothesis to verify boundary conditions and monotonicity

  - [x] 1.5 Write property tests for computation functions (Properties 6–8: Alerts, volatility, conviction)
    - **Property 6: Alert grouping counts sum to total alerts**
    - **Property 7: Trailing 20-day volatility computation matches stddev definition**
    - **Property 8: Conviction trajectory preserves round ordering**
    - **Validates: Requirements 3.1, 3.6, 4.5**
    - Implement Python equivalents of alert grouping, computeTrailing20dVol, computeConvictionTrajectory
    - Use Hypothesis with lists of alerts, price histories, and debate rounds

- [x] 2. Checkpoint - Ensure computation logic and API changes are solid
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement Autonomous Status Banner and Overview Tab
  - [x] 3.1 Add autonomous status banner to the top of the dashboard HTML
    - Enhance existing autonomous banner in dashboard.py to display:
      - Circuit breaker state (active/inactive) with intraday drawdown %
      - Last pipeline cycle timestamp
      - Overlap guard "Cycle Skipped" indicator
      - Lifetime auto-booked trade count and session count
    - Use CSS variables for styling; red/halted state when circuit breaker active
    - Fetch data from `/api/book` and `/api/logs`
    - Handle missing `session_open_nav` gracefully ("CB state unknown")
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.2 Revamp Overview tab with autonomous trading summary
    - Display KPIs: NAV, total P&L ($/%), gross/net exposure, cash %, active positions, at-risk positions
    - Add "Trims Today" count and capital freed when trims have occurred
    - Integrate equity curve chart with drawdown overlay and CB activation markers
    - Add alert count badge with highest-severity alert message
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 4. Implement Book Tab enhancements
  - [x] 4.1 Add autonomous lifecycle fields to position rows in the Book tab
    - Add trim_status color-coded badge (grey=untrimmed, amber=half_trimmed, green=fully_exited)
    - Add trail_stop_level column showing price and % distance from current price
    - Add thesis_status warning indicator with days overdue when "review_overdue"
    - Add sigma_event badge showing magnitude and threshold
    - Add expandable detail panel with trim_status, trail_stop_level, thesis_status, sigma_event columns
    - Handle missing/null fields: missing trim_status → "untrimmed", missing trail_stop → hide, missing thesis_status → "active"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Add Book tab KPI strip with portfolio summary metrics
    - Display: active positions count, positions trimmed (half_trimmed), thesis overdue count, trail stop proximity (within 1%)
    - Display: gross exposure, net exposure, average pair P&L
    - Display: aggregated capital freed by trims
    - Use computeGrossExposure, computeNetExposure, computeAveragePairPnL, computeCapitalFreedByTrims functions
    - Show "No active positions" placeholder when empty
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. Implement Risk Tab — Synthesized Dashboard
  - [x] 5.1 Build Risk tab alert summary and critical alert cards
    - Display alert summary bar grouped by severity (critical/warning/info) with counts
    - Render critical alerts prominently with red styling and recommended actions
    - Fetch from enhanced `/api/alerts` endpoint
    - _Requirements: 3.1, 3.2_

  - [x] 5.2 Build Risk tab heatmap, factor grid, and correlation/volatility sections
    - Risk heatmap grid: drawdown from peak, gross leverage, net exposure, largest concentration, sector violations — each cell color-coded
    - Factor exposure traffic-light grid using classifyFactorBeta (green < 0.4, amber 0.4–0.6, red ≥ 0.6)
    - Correlation alerts: positions with correlation > 0.5 as warning pairs
    - Trailing 20-day volatility per position using computeTrailing20dVol (show "N/A" for < 2 entries)
    - _Requirements: 3.3, 3.4, 3.5, 3.6_

- [x] 6. Checkpoint - Ensure Book and Risk tabs render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement IC Debate Tab — Decision Analysis
  - [x] 7.1 Build IC Debate tab with structured proposal cards
    - Summary card per proposal: final conviction, rounds count, majority stance, outcome (booked/rejected/pending)
    - Conviction distribution visual showing trajectory across rounds
    - Link to Book position for booked trades (click navigates to Book tab)
    - Expandable argument history with agent identities, stances, argument text
    - Agent conviction trajectory (initial → final) using computeConvictionTrajectory
    - Handle empty debates: show "No debate recorded" message
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 8. Implement Technicals Tab — Signal Summary
  - [x] 8.1 Build Technicals tab with ranked signal table and sector grouping
    - Ranked table sorted by composite score: ticker, score, trend direction, momentum classification
    - P&L annotation for tickers also in Book (cross-reference with /api/book)
    - "Weakening Technical" warning flag for scores < 40 on active positions
    - Sector grouping with sector-average scores
    - Handle scores without matching positions (display without P&L annotation)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 9. Implement Run Log Tab — Pipeline Execution Detail
  - [x] 9.1 Build Run Log tab with pipeline cycle history and per-order breakdown
    - Display each cycle: timestamp, proposals evaluated, orders passed/rejected with failing gate
    - Per-order breakdown: ticker, conviction, risk decision, PM execute, gate result (passed/failed with gate name)
    - Circuit breaker held orders flagged with drawdown %
    - Last 20 cycles by default with "Load More" pagination
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 10. Integration, error handling, and final wiring
  - [x] 10.1 Wire all tabs together with error handling and data staleness indicators
    - Ensure 30-second refresh loop re-fetches all endpoints and re-renders all panels
    - Add API fallback behavior: use embedded static data on fetch failure, show "Stale data" indicator
    - Add data staleness badge on Book tab when `_stale` is true ("Data stale — last poll {N} min ago")
    - Add "Last known" qualifier on circuit breaker when data is stale
    - Verify zero-position edge case across all tabs
    - _Requirements: 6.1, 6.2, 8.3, 8.4_

  - [x] 10.2 Write integration tests for the revamped dashboard
    - Test `/api/alerts` endpoint returns merged alerts correctly
    - Test each tab render function produces expected HTML structure with sample data
    - Test edge cases: empty positions, null autonomous fields, missing price_history, zero NAV
    - Test classification functions at exact boundaries (beta 0.39, 0.4, 0.59, 0.6)
    - _Requirements: 1.1–1.5, 2.1–2.3, 3.1–3.6, 4.1–4.5, 5.1–5.4, 6.1–6.5, 7.1–7.4, 8.1–8.4_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (Python with Hypothesis)
- Unit tests validate specific examples and edge cases
- `dashboard.py` is the primary file modified (~3000+ lines) — all HTML/CSS/JS is generated inline
- `serve.py` only needs the `/api/alerts` enhancement (task 1.1)
- The autonomous banner already exists from the autonomous-trading-loop spec — tasks enhance it, not create from scratch
- Client-side computation functions are added as JS within dashboard.py's template generation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "3.1", "3.2"] },
    { "id": 2, "tasks": ["4.1", "4.2", "5.1"] },
    { "id": 3, "tasks": ["5.2", "7.1"] },
    { "id": 4, "tasks": ["8.1", "9.1"] },
    { "id": 5, "tasks": ["10.1"] },
    { "id": 6, "tasks": ["10.2"] }
  ]
}
```
