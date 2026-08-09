# Requirements — Dashboard Modernization (Hedge Fund PMS)

## Overview
Modernize the Jimothy Capital dashboard to match the look, feel, and workflow of professional hedge fund portfolio management systems (Bloomberg PORT, Eze EMS, Aladdin, or a multi-PM pod's internal PMS). The dashboard should feel like a tool built for an analyst seat at a systematic L/S equity fund — dense, data-forward, ratio-driven, and zero fluff.

---

## R1 — Overview / Snapshot Page

**As a** PM reviewing the book pre-market,  
**I want** a single-screen snapshot showing NAV, exposure, P&L attribution, and factor tilts,  
**so that** I can assess portfolio health in under 10 seconds.

**Acceptance Criteria:**
- Top bar: NAV, daily P&L ($, bps), MTD P&L, YTD P&L, gross/net exposure, long/short counts
- Exposure breakdown: gross %, net %, beta-adjusted net
- Sector heatmap: one row per GICS sector showing net exposure, # names, daily P&L contribution
- Factor snapshot: single-row showing current beta to DXY, SPX, 10Y, VIX, CL1, Growth/Value — color-coded green/amber/red by threshold
- Drawdown indicator: current drawdown from HWM in bps
- No decorative charts unless they convey information in <2 seconds (sparklines OK, full equity curves move to a sub-tab)

---

## R2 — Trade Recommendations (Pending)

**As a** PM reviewing analyst output,  
**I want** recommendations presented as structured trade tickets with pair-ratio context,  
**so that** I can make approve/pass decisions quickly with full context visible.

**Acceptance Criteria:**
- Each recommendation is a card showing:
  - Header: Pair expression (e.g. "Long GS / Short RSPF") + direction badge
  - Parameters block: Size (% NAV), Conviction (x/10), Entry Ratio, Target Ratio, Stop Ratio, Ratio Percentile (52w), Loss@Trail (bps), Holding Period
  - Thesis: 2-3 sentence max, no scrolling
  - Variant Perception: what consensus is missing (1-2 sentences)
  - Catalyst + timeline
  - Key Risks: bullet list (3-4 max)
  - IC Verdict: badges for Tech Score, Risk Decision
- Actions: "Approve & Execute" (green) and "Pass" (muted)
- Sort by conviction descending by default
- Filter by sector

---

## R3 — Portfolio Book

**As a** PM monitoring live positions,  
**I want** a sortable table showing all open pairs with ratio-based P&L and trail proximity,  
**so that** I can identify positions needing attention.

**Acceptance Criteria:**
- Table columns: Pair (TICKER/HEDGE), Direction, Entry Ratio, Current Ratio, Peak Ratio, Pair P&L (%), Dist-from-Peak (%), Trail %, Days Held, Size (% NAV), Sector
- Color coding: P&L green/red, trail proximity amber/red when within 1%/0.5% of stop
- Expandable rows: click to see thesis, catalyst, debate summary, risk decision
- Summary row: totals for gross/net/sector breakdown
- Sparkline column: 30-day ratio history (mini SVG)

---

## R4 — Trade Blotter (Journal)

**As a** PM reviewing historical decisions,  
**I want** a chronological log of all trades (opens + closes) with linked IC context,  
**so that** I can audit past decisions and their outcomes.

**Acceptance Criteria:**
- Each entry shows: Date, Action (OPEN/CLOSE), Pair, Direction, Entry Ratio, Exit Ratio (if closed), Realized P&L, Size, Conviction
- Expandable: thesis, debate summary, tech score, risk decision — all preserved from time of execution
- Filter by: ticker, date range, action type, P&L positive/negative
- Running P&L column showing cumulative contribution

---

## R5 — IC Debate Tab

**As a** PM reviewing analyst discourse,  
**I want** debates grouped by proposal with clear challenge/defend flow,  
**so that** I can assess the quality of the investment process.

**Acceptance Criteria:**
- Grouped by proposal_id (one card per trade idea)
- Card header: Pair expression + final conviction post-debate
- Timeline view within each card: Round 1 challenges → Round 2 defense
- Each debate entry: Agent name, Stance badge (CHALLENGE/SUPPORT/DEFEND), argument text, revised conviction
- Highlight disagreements (where challenge + support coexist)

---

## R6 — Risk Tab

**As a** risk officer,  
**I want** a clear view of portfolio risk limits and per-trade risk assessments,  
**so that** I can identify breaches and concentration issues.

**Acceptance Criteria:**
- Factor beta table: 9 factors × current beta × limit × status (OK/WARNING/BREACH)
- Concentration table: by sector — # names, % NAV, limit, status
- Per-proposal risk cards (linked to recommendations): decision, rationale, size OK, hedge valid, warnings
- Total Loss-at-Trail: aggregate bps if all stops trigger simultaneously
- Leverage regime badge (Lean-In / Neutral / Cut)

---

## R7 — Technicals Tab

**As a** PM reviewing technical context,  
**I want** per-proposal technical assessments with scores and key levels,  
**so that** I can see whether technicals support or oppose the fundamental thesis.

**Acceptance Criteria:**
- One card per scored proposal
- Score bar (1-10) with color gradient
- Trend alignment, momentum regime, timing recommendation
- Active signals: chips showing golden cross, RSI, MACD, etc.
- Key levels: support/resistance in a compact grid
- Suggested entry/stop/target (ratio-based where available)

---

## R8 — Desk Assistant (Chat)

**As a** PM,  
**I want** a chat interface that connects directly to my OpenClaw agent,  
**so that** I can query the system, adjust configuration, or ask for ad-hoc analysis.

**Acceptance Criteria:**
- Messages route to OpenClaw main agent session (persistent memory)
- Responses rendered with basic markdown (bold, code, lists)
- Visible indicator that it's a live agent session, not a stateless bot
- Session ID shown for reference

---

## R9 — Visual Design Standards

**As a** user,  
**I want** the dashboard to follow institutional PMS visual conventions,  
**so that** it feels professional and information-dense.

**Acceptance Criteria:**
- Dark theme (current) — appropriate for trading floors
- Font: Inter (current) — monospace for numbers (tabular-nums)
- Dense layout: maximize information per pixel, minimize whitespace padding
- Color usage: green = positive P&L/approved, red = negative P&L/breach, gold = brand/highlight, blue = informational, amber = warning
- No emojis in data views (use geometric indicators: dots, bars, badges)
- Tables over cards where data is tabular (positions, blotter)
- Cards for narrative content (thesis, debate, recommendations)
- Mobile: functional but secondary — desktop-first design
- All financial numbers right-aligned with tabular-nums
- Timestamps in HH:MM ET format (not full ISO)

---

## R10 — Performance & Architecture

**As a** developer,  
**I want** the dashboard to be a single-page app generated from one Python source,  
**so that** there's no drift between static and served versions.

**Acceptance Criteria:**
- `dashboard.py` remains the single source of truth
- `serve.py` regenerates on each page load (current behavior)
- Auto-refresh: 30s polling for live data (current behavior)
- Page load < 1s on localhost
- No external JS dependencies — pure vanilla JS + SVG
- Total HTML size < 300KB
