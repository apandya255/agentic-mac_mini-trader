# Design — Dashboard Modernization (Hedge Fund PMS)

## Overview

Restructure the dashboard from a "trading app" aesthetic to an institutional portfolio management system. The goal is Bloomberg PORT density meets modern dark-mode design — every pixel conveys data, narrative sections (thesis, debate) are reserved for their dedicated tabs, and the overview page is purely quantitative.

---

## Layout Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  SIDEBAR (220px)              │  MAIN CONTENT                    │
│                               │                                  │
│  Jimothy Capital              │  ┌─ TOP BAR ──────────────────┐  │
│  Systematic L/S Equity        │  │ NAV │ P&L │ Gross │ Net    │  │
│                               │  └────────────────────────────┘  │
│  ─── Portfolio ───            │                                  │
│  Overview                     │  ┌─ CONTENT AREA ─────────────┐  │
│  Recommendations              │  │                             │  │
│  Book                         │  │  (tab-specific content)     │  │
│  Blotter                      │  │                             │  │
│                               │  └─────────────────────────────┘  │
│  ─── Analysis ───             │                                  │
│  IC Debate                    │                                  │
│  Risk                         │                                  │
│  Technicals                   │                                  │
│  Calendar                     │                                  │
│                               │                                  │
│  ─── History ───              │                                  │
│  Run Log                      │                                  │
│                               │                                  │
│  ─── Desk ───                 │                                  │
│  Assistant                    │                                  │
│                               │                                  │
│  [Mark to Market]             │                                  │
│  [Run IC Sweep]               │                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Tab Designs

### Overview (R1)

```
┌─────────────────────────────────────────────────────────────┐
│ TOP KPI STRIP (single row, no cards)                        │
│ NAV: $650M │ Day: +12bps │ MTD: +45bps │ YTD: +180bps     │
│ Gross: 42% │ Net: +18% │ Long: 8 │ Short: 4 │ DD: -22bps │
├─────────────────────────────────────────────────────────────┤
│ SECTOR EXPOSURE (compact table)                             │
│ Sector      │ Net %  │ Names │ Day P&L │                   │
│ Energy      │ +4.2%  │ 2     │ +8bps   │                   │
│ Financials  │ +3.5%  │ 1     │ -2bps   │                   │
│ ...         │        │       │         │                   │
├─────────────────────────────────────────────────────────────┤
│ FACTOR BETAS (single row of chips)                          │
│ [DXY -0.02] [SPX +0.03] [10Y -0.01] [VIX -0.04] ...      │
├─────────────────────────────────────────────────────────────┤
│ PENDING (count badge) │ SYSTEM HEALTH (last refresh, etc.) │
└─────────────────────────────────────────────────────────────┘
```

Key principles:
- No equity curve on overview (moved to Book tab)
- Pure numbers, no decorative elements
- Everything above the fold

### Recommendations (R2)

Each trade ticket as described in requirements. Cards stack vertically, sorted by conviction. 

Key design decisions:
- Parameters in a dark inset panel (bg-secondary) to visually separate from thesis
- Ratio fields are the primary metrics (not dollar prices)
- Thesis limited to 3 lines visible, "View full" expands
- Actions pinned to bottom of each card

### Book (R3)

Dense sortable table — the core of any PMS. 

Key design decisions:
- Table-first (not cards) — positions are tabular data
- Fixed header with sticky column for Pair name
- Ratio P&L as the primary performance column (not individual legs)
- Row background tints: amber when within 1% of trail, red within 0.5%
- Expandable rows for thesis/debate/risk context
- Equity curve moves here as a sub-section below the table

### Blotter (R4)

Chronological table of all open/close actions.

Key design decisions:
- Reverse chronological (newest first)
- Expandable rows showing full IC context (debate, tech, risk) preserved from time of trade
- Running P&L column (cumulative contribution of closed trades)
- Date grouping headers (Today, Yesterday, This Week, Earlier)

### IC Debate (R5)

Grouped by proposal — each trade idea gets its own collapsible panel.

Key design decisions:
- Collapsed by default (show pair + final conviction)
- Expand to see full debate flow
- Color-coded stance badges
- Timeline-style layout (Round 1 → Round 2)

### Risk (R6)

Two-section layout: portfolio-level limits + per-trade assessments.

Key design decisions:
- Factor table at top (always visible)
- Concentration table below
- Per-trade risk cards only show for proposals that went through the pipeline
- Breach/Warning rows highlighted with background tint

### Technicals (R7)

Per-proposal cards with score bar and signals.

Key design decisions:
- Score bar is the hero element (large, prominent)
- Signals as chips below
- Levels in a compact 2×3 grid
- Linked to the proposal_id so you know which trade it's for

---

## Files Modified

| File | Change |
|---|---|
| `dashboard.py` | Full rewrite of `build_javascript()` render functions |
| `dashboard.html` | Regenerated output (not manually edited) |
| `index.html` | Regenerated output |
| `serve.py` | No changes (API is already correct) |

---

## Implementation Approach

1. Rewrite `renderOverview()` to the dense KPI strip + sector table + factor row
2. Rewrite `renderPending()` — already done in this session (trade tickets)
3. Rewrite `renderPositions()` — clean up to pure ratio table
4. Rewrite `renderJournal()` — add linked IC context display
5. `renderDebate()` — already grouped by proposal (done this session)
6. `renderRisk()` — already per-proposal (done this session)  
7. `renderTechnical()` — already per-proposal (done this session)
8. Polish CSS: tighten padding, enforce tabular-nums everywhere, remove decorative hover effects on data tables

---

## Non-Goals

- No charting library (keep SVG-based sparklines)
- No React/Vue/framework migration
- No real-time WebSocket (30s poll is sufficient)
- No mobile-first redesign (desktop is primary)
- No authentication (local-only access)
