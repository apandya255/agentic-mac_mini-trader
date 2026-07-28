# Implementation Tasks — Portfolio Dashboard Redesign

## Phase 1: Foundation & Data Layer

### Task 1.1 — Add data formatting utilities to dashboard.py
- [x] Create JavaScript utility functions: `formatCurrency(val, decimals)`, `formatPctSigned(val)`, `pnlState(val)` returning "positive"/"negative"/"neutral", `isStale(isoTimestamp, thresholdHours)`, `classifyConfidence(score)`, `classifyRisk(decision)`
- [x] Replace all inline formatting in existing render functions with these utilities
- [x] Ensure zero renders as "neutral" not "positive"
- [x] Test: all existing panels still render correctly after refactor

### Task 1.2 — Add PortfolioSummary computation
- [x] Create `computePortfolioSummary(book, history, pending)` function in JS
- [x] Computes: nav, totalPnl ($ and %), dailyPnl ($ and %), cashPct, cashDollars, grossExposure, netExposure, drawdownPct, peakNav, riskUtilization (leverage/3.0), activePositions, pendingCount
- [x] Daily P&L derived from: sum of all position `daily_change_pct * size_pct_nav * initial_nav`
- [x] Drawdown derived from: peak NAV in history vs current NAV
- [x] Net exposure derived from: sum of long sizes - sum of short sizes (hedges are short)

### Task 1.3 — Add confirmation modal system
- [x] Create `showConfirmModal(title, message, onConfirm)` function
- [x] Modal HTML: overlay + centered card with title, message, Cancel button, Confirm button
- [x] Confirm button styled distinctly (red for destructive, green for approval)
- [x] Escape key and overlay click dismiss modal
- [x] Prevent background scroll when open
- [x] Wire into: `acceptOrder()`, `denyOrder()`, `closePosition()`

---

## Phase 2: Header & KPI Redesign

### Task 2.1 — Implement DashboardHeader
- [x] Replace current topbar with new header component
- [x] Title "Portfolio Overview" + subtitle with portfolio description
- [x] PAPER TRADING badge (amber, always visible)
- [x] Last-updated timestamp from `state.book.last_marked`
- [x] "Refresh Data" button → calls `markToMarket()` with loading spinner
- [x] "Run Agent Cycle" button → shows confirmation modal (action: placeholder, logs to console)
- [x] "Export Report" button → disabled state with tooltip "Coming soon"
- [x] Responsive: buttons stack on mobile

### Task 2.2 — Implement KPI Grid (10 cards)
- [x] Replace current `renderOverview()` metrics section with new 10-card grid
- [x] Cards: NAV, Daily P&L, Total P&L, Cash, Gross Exposure, Net Exposure, Drawdown, Risk Utilization, Active Positions, Pending Recommendations
- [x] Each card: value, subtitle, trend indicator (▲/▼/—), semantic color, ARIA label
- [x] Loading skeleton state (gray pulsing rectangle)
- [x] Unavailable state (shows "—" with gray color)
- [x] Responsive: 5-col → 3-col → 2-col grid
- [x] Pending Recommendations card links to Action Required panel (clickable)

---

## Phase 3: Action Required & Agent Consensus

### Task 3.1 — Implement Action Required Panel
- [x] New component below KPI grid (only visible when pending orders exist)
- [x] Distinct visual: left gold border, slightly elevated background
- [x] Each recommendation card: ticker, direction badge, current price (if available), size, conviction bar, rationale (truncated), risk badge, timestamp
- [x] Approve button (green) → confirmation modal → calls `acceptOrder()`
- [x] Reject button (gray, hover red) → confirmation modal → calls `denyOrder()`
- [x] "View Analysis" expands proposal detail inline (thesis, variant, risks)
- [x] Empty state: "All caught up — no pending decisions" with checkmark icon
- [x] Integrates with existing `state.pending` data

### Task 3.2 — Implement Agent Consensus Component
- [x] Compact card showing agent alignment for most recent proposal(s)
- [x] For each recent proposal with debate data: show agent stances as badges
- [x] Confidence bars (simple div width based on score/10)
- [x] Disagreement warning: amber banner when one agent challenges while others support
- [x] "View Full Debate →" link switches to debate tab
- [x] Handles missing debate data gracefully (shows "No debate data" message)
- [x] Data source: `state.debates` filtered to most recent proposal_id

---

## Phase 4: Chart & Table Redesign

### Task 4.1 — Redesign Equity Chart
- [x] Add time-range selector buttons: 1D, 1W, 1M, 3M, ALL
- [x] Filter `state.history` by selected range before rendering
- [x] Add initial-capital reference line ($10M horizontal dashed line)
- [x] Improve tooltip: show date, NAV, return % on hover (title attribute on SVG points)
- [x] Improve axis labels: more readable date format, dollar amounts with $
- [x] Empty state: "Insufficient data — mark positions daily to build history"
- [x] Error state: "Chart unavailable"
- [x] Loading skeleton: gray rectangle with pulse animation
- [x] Single data point: show as a dot with label, not a line
- [x] Optional drawdown toggle: second SVG below showing drawdown % series

### Task 4.2 — Redesign Position Table
- [x] New columns: Ticker, Direction, Status, Entry, Current, Today, Total P&L, Size, Hedge, Confidence, Days, Actions
- [x] Sortable: clicking header sorts ascending/descending (JS sort on column)
- [x] Ticker filter: input field above table filters rows by ticker substring
- [x] Sticky header: `position: sticky; top: 0` on thead
- [x] Direction badges: LONG (green), SHORT (red)
- [x] Status badges: ACTIVE (green), CLOSED (gray), STOPPED (red)
- [x] Right-align numeric columns
- [x] Expandable row: click row → shows detail panel below with thesis, agent votes, hedge info, exit criteria
- [x] "Review Position" button replaces "Close" → opens confirmation modal
- [x] Loading skeleton
- [x] Empty state
- [x] Sparkline column (existing) preserved

---

## Phase 5: System Health & Sidebar

### Task 5.1 — Implement System Health Panel
- [x] Compact row/card at bottom of overview panel
- [x] Indicators: Last Refresh (time + fresh/stale dot), Last Cycle (time), Alerts (count + severity)
- [x] Stale warning: if `last_marked` is >24h old on a weekday, show amber "Data may be stale"
- [x] Data sources: `state.book.last_marked`, `state.logs` (last cycle timestamp), alerts count
- [x] Gray dot for unknown/unavailable status
- [x] Green dot for fresh (<4h), amber for aging (4-24h), red for stale (>24h)

### Task 5.2 — Sidebar Improvements
- [x] Reduce width from 240px to 220px (update CSS variable)
- [x] "Refresh Prices" button: show spinner during refresh, show "Last: HH:MM" below
- [x] Ensure keyboard Tab navigation works through all nav items
- [x] Pending count badge already exists — ensure it updates correctly
- [x] No other sidebar changes needed for MVP

---

## Phase 6: Responsive, Accessibility & Polish

### Task 6.1 — Responsive breakpoints
- [x] Audit all new components for tablet (768-1024px) behavior
- [x] Ensure KPI grid collapses correctly
- [x] Ensure Action Required cards stack on mobile
- [x] Ensure Position Table horizontal scrolls on mobile
- [x] Ensure modals are usable on mobile (not cut off)
- [x] Test bottom nav still works with new overview content

### Task 6.2 — Accessibility pass
- [x] Add `aria-label` to all metric cards with readable descriptions
- [x] Add `role="button"` and `tabindex="0"` to clickable non-button elements
- [x] Add visible focus styles (`:focus-visible { outline: 2px solid var(--brand-gold) }`)
- [x] Ensure modal traps focus (Tab cycles within modal when open)
- [x] Add `prefers-reduced-motion` media query to disable animations
- [x] Verify color contrast meets 4.5:1 for body text

---

## Phase 7: Integration & Verification

### Task 7.1 — Regenerate and verify
- [x] Run `python3 dashboard.py --no-open` — must succeed
- [x] Run `python3 -c "from html.parser import HTMLParser; HTMLParser().feed(open('dashboard.html').read())"` — must pass
- [x] Run `python3 -c "import serve"` — no import errors
- [x] Run `python3 mark_to_market.py` — must succeed
- [x] Run `python3 monitor.py` — must succeed
- [x] Start `serve.py`, test `/api/book`, `/api/pending`, `/api/mark` — all respond correctly
- [x] Verify dashboard loads in browser without JS console errors
- [x] Verify accept/deny/close still work through the API

### Task 7.2 — Documentation
- [x] List all changed files with brief description of changes
- [x] Document architecture decisions made during implementation
- [x] List assumptions
- [x] List backend endpoints or data fields still needed for full implementation
- [x] Provide manual verification checklist (what to visually check in browser)
- [x] Do not commit until reviewed
