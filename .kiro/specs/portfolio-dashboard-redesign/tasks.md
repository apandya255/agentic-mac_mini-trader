# Implementation Tasks — Portfolio Dashboard Redesign

## Phase 1: Foundation & Data Layer

### Task 1.1 — Add data formatting utilities to dashboard.py
- [ ] Create JavaScript utility functions: `formatCurrency(val, decimals)`, `formatPctSigned(val)`, `pnlState(val)` returning "positive"/"negative"/"neutral", `isStale(isoTimestamp, thresholdHours)`, `classifyConfidence(score)`, `classifyRisk(decision)`
- [ ] Replace all inline formatting in existing render functions with these utilities
- [ ] Ensure zero renders as "neutral" not "positive"
- [ ] Test: all existing panels still render correctly after refactor

### Task 1.2 — Add PortfolioSummary computation
- [ ] Create `computePortfolioSummary(book, history, pending)` function in JS
- [ ] Computes: nav, totalPnl ($ and %), dailyPnl ($ and %), cashPct, cashDollars, grossExposure, netExposure, drawdownPct, peakNav, riskUtilization (leverage/3.0), activePositions, pendingCount
- [ ] Daily P&L derived from: sum of all position `daily_change_pct * size_pct_nav * initial_nav`
- [ ] Drawdown derived from: peak NAV in history vs current NAV
- [ ] Net exposure derived from: sum of long sizes - sum of short sizes (hedges are short)

### Task 1.3 — Add confirmation modal system
- [ ] Create `showConfirmModal(title, message, onConfirm)` function
- [ ] Modal HTML: overlay + centered card with title, message, Cancel button, Confirm button
- [ ] Confirm button styled distinctly (red for destructive, green for approval)
- [ ] Escape key and overlay click dismiss modal
- [ ] Prevent background scroll when open
- [ ] Wire into: `acceptOrder()`, `denyOrder()`, `closePosition()`

---

## Phase 2: Header & KPI Redesign

### Task 2.1 — Implement DashboardHeader
- [ ] Replace current topbar with new header component
- [ ] Title "Portfolio Overview" + subtitle with portfolio description
- [ ] PAPER TRADING badge (amber, always visible)
- [ ] Last-updated timestamp from `state.book.last_marked`
- [ ] "Refresh Data" button → calls `markToMarket()` with loading spinner
- [ ] "Run Agent Cycle" button → shows confirmation modal (action: placeholder, logs to console)
- [ ] "Export Report" button → disabled state with tooltip "Coming soon"
- [ ] Responsive: buttons stack on mobile

### Task 2.2 — Implement KPI Grid (10 cards)
- [ ] Replace current `renderOverview()` metrics section with new 10-card grid
- [ ] Cards: NAV, Daily P&L, Total P&L, Cash, Gross Exposure, Net Exposure, Drawdown, Risk Utilization, Active Positions, Pending Recommendations
- [ ] Each card: value, subtitle, trend indicator (▲/▼/—), semantic color, ARIA label
- [ ] Loading skeleton state (gray pulsing rectangle)
- [ ] Unavailable state (shows "—" with gray color)
- [ ] Responsive: 5-col → 3-col → 2-col grid
- [ ] Pending Recommendations card links to Action Required panel (clickable)

---

## Phase 3: Action Required & Agent Consensus

### Task 3.1 — Implement Action Required Panel
- [ ] New component below KPI grid (only visible when pending orders exist)
- [ ] Distinct visual: left gold border, slightly elevated background
- [ ] Each recommendation card: ticker, direction badge, current price (if available), size, conviction bar, rationale (truncated), risk badge, timestamp
- [ ] Approve button (green) → confirmation modal → calls `acceptOrder()`
- [ ] Reject button (gray, hover red) → confirmation modal → calls `denyOrder()`
- [ ] "View Analysis" expands proposal detail inline (thesis, variant, risks)
- [ ] Empty state: "All caught up — no pending decisions" with checkmark icon
- [ ] Integrates with existing `state.pending` data

### Task 3.2 — Implement Agent Consensus Component
- [ ] Compact card showing agent alignment for most recent proposal(s)
- [ ] For each recent proposal with debate data: show agent stances as badges
- [ ] Confidence bars (simple div width based on score/10)
- [ ] Disagreement warning: amber banner when one agent challenges while others support
- [ ] "View Full Debate →" link switches to debate tab
- [ ] Handles missing debate data gracefully (shows "No debate data" message)
- [ ] Data source: `state.debates` filtered to most recent proposal_id

---

## Phase 4: Chart & Table Redesign

### Task 4.1 — Redesign Equity Chart
- [ ] Add time-range selector buttons: 1D, 1W, 1M, 3M, ALL
- [ ] Filter `state.history` by selected range before rendering
- [ ] Add initial-capital reference line ($10M horizontal dashed line)
- [ ] Improve tooltip: show date, NAV, return % on hover (title attribute on SVG points)
- [ ] Improve axis labels: more readable date format, dollar amounts with $
- [ ] Empty state: "Insufficient data — mark positions daily to build history"
- [ ] Error state: "Chart unavailable"
- [ ] Loading skeleton: gray rectangle with pulse animation
- [ ] Single data point: show as a dot with label, not a line
- [ ] Optional drawdown toggle: second SVG below showing drawdown % series

### Task 4.2 — Redesign Position Table
- [ ] New columns: Ticker, Direction, Status, Entry, Current, Today, Total P&L, Size, Hedge, Confidence, Days, Actions
- [ ] Sortable: clicking header sorts ascending/descending (JS sort on column)
- [ ] Ticker filter: input field above table filters rows by ticker substring
- [ ] Sticky header: `position: sticky; top: 0` on thead
- [ ] Direction badges: LONG (green), SHORT (red)
- [ ] Status badges: ACTIVE (green), CLOSED (gray), STOPPED (red)
- [ ] Right-align numeric columns
- [ ] Expandable row: click row → shows detail panel below with thesis, agent votes, hedge info, exit criteria
- [ ] "Review Position" button replaces "Close" → opens confirmation modal
- [ ] Loading skeleton
- [ ] Empty state
- [ ] Sparkline column (existing) preserved

---

## Phase 5: System Health & Sidebar

### Task 5.1 — Implement System Health Panel
- [ ] Compact row/card at bottom of overview panel
- [ ] Indicators: Last Refresh (time + fresh/stale dot), Last Cycle (time), Alerts (count + severity)
- [ ] Stale warning: if `last_marked` is >24h old on a weekday, show amber "Data may be stale"
- [ ] Data sources: `state.book.last_marked`, `state.logs` (last cycle timestamp), alerts count
- [ ] Gray dot for unknown/unavailable status
- [ ] Green dot for fresh (<4h), amber for aging (4-24h), red for stale (>24h)

### Task 5.2 — Sidebar Improvements
- [ ] Reduce width from 240px to 220px (update CSS variable)
- [ ] "Refresh Prices" button: show spinner during refresh, show "Last: HH:MM" below
- [ ] Ensure keyboard Tab navigation works through all nav items
- [ ] Pending count badge already exists — ensure it updates correctly
- [ ] No other sidebar changes needed for MVP

---

## Phase 6: Responsive, Accessibility & Polish

### Task 6.1 — Responsive breakpoints
- [ ] Audit all new components for tablet (768-1024px) behavior
- [ ] Ensure KPI grid collapses correctly
- [ ] Ensure Action Required cards stack on mobile
- [ ] Ensure Position Table horizontal scrolls on mobile
- [ ] Ensure modals are usable on mobile (not cut off)
- [ ] Test bottom nav still works with new overview content

### Task 6.2 — Accessibility pass
- [ ] Add `aria-label` to all metric cards with readable descriptions
- [ ] Add `role="button"` and `tabindex="0"` to clickable non-button elements
- [ ] Add visible focus styles (`:focus-visible { outline: 2px solid var(--brand-gold) }`)
- [ ] Ensure modal traps focus (Tab cycles within modal when open)
- [ ] Add `prefers-reduced-motion` media query to disable animations
- [ ] Verify color contrast meets 4.5:1 for body text

---

## Phase 7: Integration & Verification

### Task 7.1 — Regenerate and verify
- [ ] Run `python3 dashboard.py --no-open` — must succeed
- [ ] Run `python3 -c "from html.parser import HTMLParser; HTMLParser().feed(open('dashboard.html').read())"` — must pass
- [ ] Run `python3 -c "import serve"` — no import errors
- [ ] Run `python3 mark_to_market.py` — must succeed
- [ ] Run `python3 monitor.py` — must succeed
- [ ] Start `serve.py`, test `/api/book`, `/api/pending`, `/api/mark` — all respond correctly
- [ ] Verify dashboard loads in browser without JS console errors
- [ ] Verify accept/deny/close still work through the API

### Task 7.2 — Documentation
- [ ] List all changed files with brief description of changes
- [ ] Document architecture decisions made during implementation
- [ ] List assumptions
- [ ] List backend endpoints or data fields still needed for full implementation
- [ ] Provide manual verification checklist (what to visually check in browser)
- [ ] Do not commit until reviewed
