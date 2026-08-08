# Implementation Plan: Dashboard Bootstrap Alignment

## Overview

Align the portfolio dashboard with the operational bootstrap framework by adding 10 enhancements: pair-ratio position display, trail/target proximity indicators, factor beta exposure table, leverage regime badge, flip-condition display, full pitch format for pending orders, loss-at-trail KPIs, conviction tier tagging, desk calendar integration, and concentration limits display. All computation is client-side JavaScript; only 2-3 new API endpoints are added to `serve.py`.

## Tasks

- [x] 1. Backend API additions (`serve.py`)
  - [x] 1.1 Add `/api/calendar` endpoint that parses `desk/calendar.md`
    - Read `desk/calendar.md`, split by `###` section headers (Macro releases, CB decisions, Earnings, Holidays)
    - Parse markdown table rows within each section into structured JSON arrays
    - Return `{ "macro": [...], "cb": [...], "earnings": [...], "holidays": [...], "empty": bool }`
    - If file is missing or all sections are empty/placeholder (`| — |`), return `{ "empty": true, ... }`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

  - [x] 1.2 Add `/api/factors` endpoint for factor beta data
    - Read `memos/state/factors.json` if it exists
    - Return `{ "available": true, "computed_at": "...", "factors": { "USD_DXY": 0.12, ... } }` with all 9 factor keys
    - If file does not exist, return `{ "available": false, "factors": {} }`
    - _Requirements: 3.1, 3.2, 3.7_

  - [x] 1.3 Add `leverage_regime` field to `/api/book` response
    - After `mark_positions_to_market`, read latest risk assessment from `memos/risk/` for the `leverage_regime` field
    - Add `book["leverage_regime"]` to the response (default to `null` if unavailable)
    - _Requirements: 4.1, 4.5_

- [x] 2. Client-side computation module (JavaScript in `dashboard.py`)
  - [x] 2.1 Implement `computeDerivedMetrics(state)` function and helper utilities
    - Add `HEDGE_TO_SECTOR` mapping constant (11 GICS sectors from hedge ETF tickers)
    - Implement `round4(x)` utility for 4-decimal rounding
    - Implement `parseTrailPct(stopLossMethod)` to extract numeric trail percentage from strings like "trailing 2.5% from peak"
    - Implement `computeDerivedMetrics(state)` that iterates active positions and computes: entryRatio, currentRatio, peakRatio, pnlPct, distFromPeak, distToTarget, trailPct, lossAtTrail, highlight, isHighConviction, sector
    - Compute `totalLossAtTrail` as sum of individual lossAtTrail values
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 7.1, 7.2_

  - [x] 2.2 Implement classification functions
    - `classifyProximity(distFromPeak, trailPct)` → red/amber/normal based on gap to trail trigger
    - `classifyBeta(beta)` → red (>0.6) / amber (>0.4) / normal
    - `regimeColor(regime)` → green/gray/red mapping
    - `computeConcentration(positions)` → sector grouping with count, navPct, and highlight classification
    - `filterFactorDeltas(deltas)` → filter entries with |value| > 0.1
    - _Requirements: 2.4, 2.5, 3.3, 3.4, 4.2, 4.3, 4.4, 6.7, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 2.3 Write property tests for computation functions (fast-check)
    - **Property 1: Ratio computation correctness**
    - **Property 2: P&L derived from ratios, not legs**
    - **Property 3: Peak ratio is monotonic for longs**
    - **Property 4: Distance-from-peak computation**
    - **Property 5: Distance-to-target computation**
    - **Property 6: Trail proximity classification is exhaustive and mutually exclusive**
    - **Property 7: Factor beta classification is exhaustive and mutually exclusive**
    - **Property 8: Leverage regime color mapping is total**
    - **Property 9: Loss-at-trail computation**
    - **Property 10: Total loss-at-trail is the sum of individual positions**
    - **Property 11: Conviction tier classification threshold**
    - **Property 12: Factor delta filtering**
    - **Property 13: Concentration grouping correctness**
    - **Property 14: Concentration threshold classification**
    - **Validates: Requirements 1.1–1.5, 2.2–2.5, 3.3–3.6, 4.2–4.4, 7.1–7.2, 8.1, 8.3, 10.1–10.6**

- [x] 3. Checkpoint - Ensure backend endpoints work and computation module is correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Position table enhancements (`renderPositions` in `dashboard.py`)
  - [x] 4.1 Add pair-ratio columns and P&L-from-ratio to position table
    - Add new columns: Entry Ratio, Current Ratio, Peak Ratio, Pair P&L (%), Trail %, Dist Peak, Dist Target, Loss@Trail (bps)
    - Call `computeDerivedMetrics(state)` and use enriched position data for rendering
    - Display "—" for any field that cannot be computed (missing hedge price, null trail, etc.)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 7.1, 7.3_

  - [x] 4.2 Add trail proximity highlights and conviction badges to position rows
    - Apply red/amber CSS background classes to position rows based on `highlight` classification
    - Add gold border + "HIGH CONVICTION" badge for positions with `size_pct_nav > 0.05`
    - Add conviction tier indicator column with distinct icon
    - _Requirements: 2.4, 2.5, 8.1, 8.3_

  - [x] 4.3 Add flip condition and conviction memo to expanded position detail
    - In `renderPositionDetailPanel`, add "Flip Condition" field showing `order._proposal.flip_condition` or "Not specified"
    - For high-conviction positions, display the "why this deserves size" memo from proposal or "Memo not available"
    - _Requirements: 5.1, 5.2, 5.3, 8.2, 8.4_

- [x] 5. Risk tab enhancements (`renderRisk` in `dashboard.py`)
  - [x] 5.1 Add factor beta exposure table to Risk tab
    - Fetch `/api/factors` in `refreshAll()`
    - Render a 9-row table with factor name and beta value (2dp)
    - Apply amber/red cell highlights using `classifyBeta()`
    - If `available === false`, show "—" in each cell with a "pending" label
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

  - [x] 5.2 Add concentration limits table to Risk tab
    - Render sector concentration table showing: sector name, position count vs max 4, NAV % vs max 15%
    - Apply red highlight for count >= 4, amber for count == 3 or navPct > 12%
    - Add country concentration section with "Country data pending" placeholder
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 6. Overview tab enhancements (`renderOverview` in `dashboard.py`)
  - [x] 6.1 Add leverage regime badge to Overview tab
    - Render badge in system health panel with text from `state.book.leverage_regime`
    - Apply green/gray/red background via `regimeColor()`
    - Show "—" with gray background if unavailable
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 6.2 Add factor warnings summary and total loss-at-trail KPI to Overview tab
    - Add compact factor summary widget showing any factors with |beta| > 0.4 (amber or red)
    - Add "Total Loss-at-Trail" KPI card showing sum in bps
    - _Requirements: 3.6, 7.2_

  - [x] 6.3 Add compact calendar widget to Overview tab
    - Fetch `/api/calendar` in `refreshAll()`
    - Render compact calendar showing upcoming events grouped by type (macro, cb, earnings)
    - Display "No calendar data available" when `calendarData.empty === true`
    - _Requirements: 9.1, 9.6_

- [x] 7. Pending orders tab — full pitch format (`renderPending` in `dashboard.py`)
  - [x] 7.1 Rewrite pending order rendering to use full pitch telegram format
    - Display thesis (3 lines max) from `order._proposal.thesis` or `order._proposal.portfolio_thesis`
    - Display best counter-argument (1 line) from `order._proposal.best_counter`
    - Display entry/stop/target levels with numeric values
    - Display size (% NAV) and loss-at-trail (bps)
    - Display technical score (X/10) with key levels
    - Display risk verdict (PASS/RESIZE/REJECT)
    - Display factor deltas filtered to |delta| > 0.1
    - Show "—" for any missing field
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 8. Calendar section — full view
  - [x] 8.1 Add Calendar tab/section to sidebar navigation and panel
    - Add "Calendar" nav item in sidebar between "Risk" and "Technical" (or after Technical)
    - Create `panel-calendar` div in main shell
    - Implement `renderCalendar()` function that renders full calendar by category (macro, cb, earnings, holidays)
    - Display tables grouped by event type with all fields per the schema
    - Display "No calendar data available" for empty state
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 9. Checkpoint - Verify full integration
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 10. Unit and integration tests
  - [ ]* 10.1 Write unit tests for computation functions
    - Test missing peak_ratio defaults to entry_ratio
    - Test factor table has exactly 9 rows
    - Test factor display shows "—" when unavailable
    - Test leverage regime "—" when unavailable
    - Test flip condition "Not specified" when missing
    - Test pitch fields show "—" when missing
    - Test loss-at-trail shows "—" when trail_pct is null
    - Test conviction memo "Memo not available" when missing
    - Test calendar shows "No calendar data available" for empty/placeholder content
    - Test country section shows "Country data pending" when unavailable
    - _Requirements: 1.5, 3.1, 3.7, 4.5, 5.3, 6.8, 7.3, 8.4, 9.6, 10.7_

  - [ ]* 10.2 Write integration tests for new API endpoints
    - Test `/api/calendar` returns valid JSON with expected schema
    - Test `/api/factors` returns `available: false` when no `factors.json` exists
    - Test `/api/book` response includes `leverage_regime` field
    - _Requirements: 3.7, 4.5, 9.6_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All new rendering is client-side JavaScript embedded in `dashboard.py`; only `serve.py` gets new endpoints
- The design specifies the computation module could be extracted to `src/dashboard/computations.js` for testability — this is deferred to optional test tasks
- Calendar event schema follows: macro (day, time, currency, release, consensus, seat), cb (date, currency, action), earnings (date, timing, ticker, seat), holidays (date, name, type)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["4.1", "5.1", "6.1", "7.1", "8.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "5.2", "6.2", "6.3"] },
    { "id": 5, "tasks": ["10.1", "10.2"] }
  ]
}
```
