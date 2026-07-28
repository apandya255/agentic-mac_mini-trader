# Agentic AI Trading System — POC Design Document

**Version:** 0.1 (Proof of Concept)
**Date:** 2026-07-27
**Classification:** Internal
**Scope:** Small-scale POC on MacBook Pro using OpenClaw as agent manager. Energy sector only, 5 agents.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Objectives & Constraints](#2-system-objectives--constraints)
3. [Universe Specification](#3-universe-specification)
4. [Agent Architecture](#4-agent-architecture)
5. [Fundamental Agent (×1)](#5-fundamental-agent)
6. [Macro Agent (×1)](#6-macro-agent)
7. [Technical Agent (×1)](#7-technical-agent)
8. [Risk Management Agent](#8-risk-management-agent)
9. [Portfolio Management Agent](#9-portfolio-management-agent)
10. [Investment Process & Debate Protocol](#10-investment-process--debate-protocol)
11. [Hedging Framework](#11-hedging-framework)
12. [Risk Management Framework](#12-risk-management-framework)
13. [Data Architecture](#13-data-architecture)
14. [State Management & Persistence](#14-state-management--persistence)
15. [Orchestration & Scheduling](#15-orchestration--scheduling)
16. [Delivery & Interaction Layer](#16-delivery--interaction-layer)
17. [Infrastructure & Deployment](#17-infrastructure--deployment)
18. [Security & Access](#18-security--access)
19. [Monitoring & Observability](#19-monitoring--observability)
20. [Performance & Scaling](#20-performance--scaling)
21. [Failure Modes & Recovery](#21-failure-modes--recovery)
22. [Cost Model](#22-cost-model)
23. [Development Phases](#23-development-phases)

---

## 1. Executive Summary

This document specifies the POC architecture for a small-scale multi-agent AI trading system running on a MacBook Pro using **OpenClaw** as the agent manager. The system employs 5 agents — 1 energy fundamental analyst, 1 commodities macro analyst, 1 technical analyst, 1 risk manager, and 1 portfolio manager — operating within a structured debate and approval pipeline.

The POC validates:
- Agent communication via OpenClaw's isolated session architecture
- The debate protocol (blind first pass → memo exchange)
- Risk gating with factor beta enforcement
- End-to-end pipeline producing a hedged trade recommendation

OpenClaw provides system-level access, session isolation, and the Gateway for routing agent invocations. Our `data_platform` modules (12 Python files + CLI) serve as the tool layer agents call via shell commands.

---

## 2. System Objectives & Constraints

### Performance Targets (Paper Trading)
- Annualized return target: 12–15%+
- Downside volatility: ≤6% annualized
- Position stop-loss: 2–3% trailing from peak
- Position gain target: 5% (PM review trigger)
- Sharpe ratio implied: ≥2.0

### Structural Constraints
- Every position must be hedged (no naked directional exposure)
- Combined book factor beta: ≤ ±0.6 to any single factor
- Factors tracked: DXY, SPX, USGG10Yr, VIX, Growth/Value, CL1, Large/Small cap, CDX HY 5Y, XAU
- Sizing: 2–5% by conviction; high-conviction tier up to 8% (max 2 slots)
- Circuit breaker: 4% warning / 6% hard stop from peak NAV
- Agents may hold cash (no forced investment)

### Operational Constraints
- Runs on MacBook Pro (personal device)
- OpenClaw as agent manager (isolated sessions, shell tool access)
- No auto-execution — all trades are paper/discretionary
- Full audit trail (debate transcripts, risk decisions, trade journal)
- NAV: $10mm (paper) for POC

---

## 3. Universe Specification

### 3.1 Equities (Energy Sector Only)

| Ticker | Company | Sub-Sector |
|--------|---------|-----------|
| XOM | Exxon Mobil | Integrated |
| CVX | Chevron | Integrated |
| COP | ConocoPhillips | E&P |
| EOG | EOG Resources | E&P |
| SLB | Schlumberger | Services |
| MPC | Marathon Petroleum | Refining |
| PSX | Phillips 66 | Refining |
| VLO | Valero Energy | Refining |
| OXY | Occidental Petroleum | E&P |
| DVN | Devon Energy | E&P |

### 3.2 Sector ETFs

| ETF | Description | Role |
|-----|-------------|------|
| XLE | Energy Select Sector SPDR | Sector expression |
| RSPG | Invesco S&P 500 EW Energy | Single-name hedge |
| RSP | Invesco S&P 500 Equal Weight | Sector ETF hedge |

### 3.3 Commodities

| Asset | Vehicle | Role |
|-------|---------|------|
| Oil (WTI) | USO | Commodity expression |
| Oil Producers | XOP | Producer ETF expression |
| Gold | GLD | Cross-asset reference |

### 3.4 Broad Hedges
- RSP (equal-weight S&P 500) — hedge for XLE-level trades
- RSPG (equal-weight energy) — hedge for single-name trades
- ACWI — universal broad hedge

### 3.5 Factor Proxies (for beta computation)
UUP, SPY, IEF, VIXY, IWF, IWD, USO, IWB, IWM, HYG, GLD

---

## 4. Agent Architecture

### 4.1 High-Level Topology (OpenClaw)

```
┌─────────────────────────────────────────────────────────┐
│              OPENCLAW GATEWAY (MacBook Pro)               │
│         (Routes requests, manages sessions)              │
└──────────────────────────┬──────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
   ┌─────▼─────┐   ┌──────▼──────┐   ┌─────▼──────┐
   │  SHARED    │   │  PIPELINE   │   │   DATA     │
   │ FILESYSTEM │   │   STATE     │   │  PLATFORM  │
   │ (memos/)   │   │ (book.json) │   │  (CLI)     │
   └─────┬──────┘   └─────────────┘   └─────┬──────┘
         │                                    │
   ┌─────┼────────────────────────────────────┼─────┐
   │     │       AGENT RUNTIMES (×5)          │     │
   │  ┌──▼────────────────────────────────┐   │     │
   │  │  fund_energy (isolated session)   │◄──┤     │
   │  └──────────────────────────────────-┘   │     │
   │  ┌───────────────────────────────────┐   │     │
   │  │  macro_commodities (isolated)     │◄──┤     │
   │  └───────────────────────────────────┘   │     │
   │  ┌───────────────────────────────────┐   │     │
   │  │  tech_equity (isolated)           │◄──┤     │
   │  └───────────────────────────────────┘   │     │
   │  ┌───────────────────────────────────┐   │     │
   │  │  risk_management (isolated)       │◄──┘     │
   │  └───────────────────────────────────┘         │
   │  ┌───────────────────────────────────┐         │
   │  │  portfolio_manager (isolated)     │◄────────┘
   │  └───────────────────────────────────┘
   └────────────────────────────────────────────────┘
```

### 4.2 OpenClaw Session Model

Each agent runs as an **isolated OpenClaw session** with:
- Its own mandate (markdown system prompt)
- Shell access to `data_platform` CLI tools
- Read/write access to a shared `memos/` directory for debate exchange
- Read access to `state/book.json` for current portfolio state
- No direct communication with other agents (blind first pass)

### 4.3 Agent Invocation Pattern

```bash
# OpenClaw invokes each agent via its runtime
# Agent reads its mandate, calls tools, writes output

# Example: fund_energy agent cycle
openclaw run fund_energy --mandate mandates/fund_energy.md \
  --tools tools/ \
  --output memos/proposals/
```

### 4.4 Tool Access (via data_platform CLI)

Each agent can call:
```bash
python -m data_platform.cli prices returns --ticker XOM
python -m data_platform.cli technicals scan --ticker XOM
python -m data_platform.cli valuations snapshot --ticker XOM
python -m data_platform.cli risk trailing-stop --ticker XOM ...
python -m data_platform.cli universe hedge --ticker XOM --direction long
python -m data_platform.cli sizing compute --conviction 8
python -m data_platform.cli macro indicator --name WTI_CRUDE
python -m data_platform.cli news headlines --ticker XOM
```

All output is JSON — parseable by the LLM within the OpenClaw session.

---

## 5. Fundamental Agent (×1)

### 5.1 Identity
- **Agent ID:** fund_energy
- **Sector:** Energy
- **Coverage:** XOM, CVX, COP, EOG, SLB, MPC, PSX, VLO, OXY, DVN + XLE (sector level)

### 5.2 Analytical Framework

Core Process:
1. Model Building — production growth, breakevens, refining margins, capex discipline, shareholder returns
2. Valuation — EV/EBITDA, P/FCF, dividend yield vs. peers and own history
3. Variant Perception — where our estimates diverge from consensus
4. Catalyst Identification — earnings, OPEC decisions, regulatory, capex announcements
5. Position Construction — long or short with RSPG hedge (single name) or RSP hedge (XLE)

KPIs: production_growth, reserve_life, breakeven_price, rig_count_trend, refining_margins, capex_discipline, shareholder_return_yield

Drivers: oil_price, gas_price, opec_policy, us_shale_activity, energy_transition

### 5.3 Tools Available
- `prices returns --ticker <T>` — trailing returns
- `prices pair-ratio --ticker <T> --hedge RSPG` — pair ratio context
- `valuations snapshot --ticker <T>` — P/E, EV/EBITDA, margins, analyst targets
- `valuations peers --ticker <T> --peers CVX COP EOG SLB` — relative value
- `news headlines --ticker <T>` — recent news
- `technicals scan --ticker <T>` — quick technical check (not its primary job)

### 5.4 Output
Writes a `TradeProposal` JSON to `memos/proposals/fund_energy_<timestamp>.json`

---

## 6. Macro Agent (×1)

### 6.1 Identity
- **Agent ID:** macro_commodities
- **Region/Product:** Oil & Gas, Gold (commodity macro view)
- **Coverage:** USO, XOP, GLD + energy sector implications

### 6.2 Analytical Framework

Core Process:
1. Supply/Demand Balance — OPEC policy, US production, global demand trajectory
2. Inventory & Curve — crude inventories, contango vs. backwardation
3. Cost Curve — marginal producer breakevens, capex cycle
4. USD Correlation — DXY impact on commodity pricing
5. Geopolitical Supply Risk — Middle East, Russia, sanctions
6. Expression Selection — XLE, USO, XOP, or single-name via fundamental agent

Key Drivers: supply_demand_balance, inventory_levels, cost_curve, futures_curve_shape, USD_correlation, china_demand_impulse, geopolitical_supply_risk

### 6.3 Tools Available
- `macro indicator --name WTI_CRUDE` — oil price from FRED
- `macro indicator --name DXY_BROAD` — dollar index
- `prices returns --ticker USO` — oil ETF performance
- `prices pair-ratio --ticker XLE --hedge RSP` — energy vs. broad market
- `news headlines --ticker XLE` — sector news
- `news macro-events --days 14` — upcoming catalysts

### 6.4 Output
Writes a `MacroTradeProposal` JSON to `memos/proposals/macro_commodities_<timestamp>.json`

---

## 7. Technical Agent (×1)

### 7.1 Identity
- **Agent ID:** tech_equity
- **Coverage:** All POC universe tickers (10 names + ETFs + commodities)

### 7.2 Analytical Framework

Signals: MA crossovers (20/50/100/200), RSI, MACD, KST, ADX, Bollinger Bands, ATR, OBV, Fibonacci retracements, volume confirmation, relative strength.

Responsibilities:
1. Score proposals from fund_energy and macro_commodities on technicals (1–10)
2. Provide entry, stop, and target levels
3. Identify CTA trigger levels and flow context
4. Surface purely technical setups (must be debated before PM reviews)

### 7.3 Tools Available
- `technicals scan --ticker <T>` — full technical snapshot (primary tool)
- `prices history --ticker <T> --lookback 20` — recent price action
- `prices pair-ratio --ticker <T> --hedge <H>` — ratio technicals
- `prices relative-strength --ticker <T> --benchmark SPY`

### 7.4 Output
Writes a `TechnicalScore` JSON to `memos/scores/tech_<proposal_id>.json`

---

## 8. Risk Management Agent

### 8.1 Role & Authority
Gatekeeper. No trade enters the book without approval. Empowered to reject or modify any proposal regardless of conviction. Runs on a **different model family** than the originating agent (per partner spec).

### 8.2 Risk Framework

```yaml
position_level:
  max_position_size: 5% NAV (single name), 8% NAV (ETF/HC)
  stop_loss: 2-3% trailing from peak (no fixed stops)
  gain_target: 5% triggers PM review (take is default)
  max_sector_concentration: 25% gross
  correlation_limit: avoid >0.7 between active positions

portfolio_level:
  factor_beta_limit: ±0.6 per factor
  max_gross_leverage: 3.0x
  target_net_exposure: ±0.3
  circuit_breaker: 4% warning / 6% hard stop
  max_downside_volatility: 6% annualized
```

### 8.3 Tools Available
- `risk circuit-breaker --nav <current_nav>` — drawdown status
- `risk trailing-stop --ticker <T> --direction <D> --entry-price <E> --peak-price <P> --current-price <C>` — stop levels
- `risk correlation --tickers <T1> <T2> <T3>` — pairwise correlations
- `risk crowding --tickers <T1> <T2> <T3>` — cluster detection
- `sizing compute --conviction <N>` — check max allowed size

### 8.4 Output
Writes a `RiskDecision` JSON to `memos/risk/risk_<proposal_id>.json`

---

## 9. Portfolio Management Agent

### 9.1 Role & Authority
Final decision-maker. Receives risk-approved proposals, sizes trades, sets parameters, decides execute or pass.

### 9.2 Decision Framework

```yaml
pm_decision_criteria:
  conviction_threshold: 6
  technical_score_threshold: 5
  
  sizing_model:
    conviction_1-4: 2% NAV
    conviction_5-6: 3% NAV
    conviction_7-8: 4% NAV
    conviction_9-10: 5% NAV
    high_conviction: 8% NAV (max 2 slots)
  
  exit_framework:
    trailing_stop_hit: immediate exit
    target_reached_5pct: take profit default (extending requires re-affirmed flip-condition)
    thesis_invalidated: exit regardless of P&L
    60_days_no_catalyst: reassess
```

### 9.3 Tools Available
- `sizing compute --conviction <N>` — position size
- `sizing table` — full sizing regime
- `risk circuit-breaker --nav <NAV>` — current regime
- `carry cash --cash-pct <P>` — carry impact
- `carry position-cost --direction <D> --notional <N>` — cost of trade

### 9.4 Output
Writes a `TradeOrder` JSON to `memos/orders/order_<proposal_id>.json`

---

## 10. Investment Process & Debate Protocol

### 10.1 Idea Generation (POC: Manual Trigger)

In the POC, cycles are triggered manually via:
```bash
python run_cycle.py
```

This runs all 5 agents in sequence through the pipeline.

### 10.2 Debate Protocol — OpenClaw Implementation

```
┌────────────────────────────────────────────────────────────┐
│                 POC DEBATE PROTOCOL                          │
├────────────────────────────────────────────────────────────┤
│                                                              │
│  PHASE 1: BLIND FIRST PASS                                  │
│  ├── fund_energy runs in isolated session → writes proposal │
│  ├── macro_commodities runs in isolated session → writes    │
│  │   proposal (independently, no visibility to fund_energy) │
│  └── Each writes to memos/proposals/                        │
│                                                              │
│  PHASE 2: MEMO EXCHANGE (Debate)                            │
│  ├── fund_energy reads macro_commodities' proposal          │
│  │   → writes challenge/support to memos/debate/            │
│  ├── macro_commodities reads fund_energy's proposal         │
│  │   → writes challenge/support to memos/debate/            │
│  ├── Originator responds to challenges (round 2)           │
│  └── Max 3 rounds, then conviction check                   │
│                                                              │
│  PHASE 3: CONVICTION CHECK                                  │
│  ├── conviction < 5 → withdrawn                            │
│  ├── conviction 5-6 → proceeds (lower priority)            │
│  └── conviction ≥ 7 → proceeds to technical scoring        │
│                                                              │
│  PHASE 4: TECHNICAL SCORING                                 │
│  ├── tech_equity reads surviving proposals                  │
│  ├── Runs full technical scan on each                       │
│  └── Writes TechnicalScore to memos/scores/                │
│                                                              │
│  PHASE 5: RISK GATE                                         │
│  ├── risk_management reads proposals + scores              │
│  ├── Checks factor betas, correlation, circuit breaker     │
│  ├── Writes RiskDecision (approved/rejected/modified)      │
│  └── Uses DIFFERENT MODEL than originator                   │
│                                                              │
│  PHASE 6: PM DECISION                                       │
│  ├── portfolio_manager reads approved proposals            │
│  ├── Sizes trade, sets stops/targets                       │
│  └── Writes TradeOrder to memos/orders/                    │
│                                                              │
└────────────────────────────────────────────────────────────┘
```

### 10.3 File-Based Communication (OpenClaw Pattern)

```
memos/
├── proposals/          # Written by fund_energy and macro_commodities
│   ├── fund_energy_2026-07-27T08-00.json
│   └── macro_commodities_2026-07-27T08-00.json
├── debate/             # Challenge/support messages
│   ├── fund_energy_re_macro_001.json
│   └── macro_commodities_re_fund_001.json
├── scores/             # Technical scores
│   └── tech_proposal_001.json
├── risk/               # Risk decisions
│   └── risk_proposal_001.json
├── orders/             # Final trade orders
│   └── order_proposal_001.json
└── state/
    └── book.json       # Current portfolio state
```

Each agent reads from and writes to these directories. OpenClaw's isolated sessions ensure agents can only see what the orchestrator exposes to them at each phase.

### 10.4 Debate Rules
1. Evidence requirement: cite specific data points from tool calls
2. Max 3 rounds of exchange
3. Conviction < 5 after debate → auto-withdraw
4. Agent cannot debate its own proposal (only respond to challenges)
5. Risk gate runs on different model family than originator

---

## 11. Hedging Framework

### 11.1 POC Hedge Rules

| Trade Type | Hedge |
|-----------|-------|
| Single name (XOM, CVX, etc.) long | Short RSPG |
| Single name short | Long RSPG |
| XLE long | Short RSP |
| XLE short | Long RSP |
| USO/XOP long | Short ACWI (or RSP per PM) |
| USO/XOP short | Long ACWI (or RSP per PM) |

### 11.2 Hedge Sizing
Default: dollar-neutral (equal notional both legs). PM may adjust for beta.

### 11.3 Book Representation
Per partner spec: every position is one line at a level, pairs as the ratio.
```
XOM/RSPG @ 1.1864  +1.8%  [8/10 S]  long 4.0%  trail@103.25
XLE/RSP @ 0.5452   +2.1%  [7/10 S]  long 3.0%  trail@87.50
```

---

## 12. Risk Management Framework

### 12.1 Factor Beta Monitoring
Rolling 252-day univariate OLS against 9 factors. Hard limit: |beta| ≤ 0.6.

### 12.2 Drawdown Management (POC: $10mm NAV)

| Drawdown | Action |
|----------|--------|
| 0% – 4% | Normal operations |
| 4% – 6% | Warning: reduce sizing 20%, review lowest-conviction |
| 6%+ | Circuit breaker: halt new positions, deleverage to 0.3x |
| Recovery | Re-lever after 5 consecutive positive days |

### 12.3 Position-Level Risk
- Trailing stop: 2–3% from peak (ratchets up, never down)
- +5% gain: PM review (take is default)
- Max holding without catalyst: 60 days
- Max single position: 5% NAV (8% for HC tier)

### 12.4 Correlation & Crowding
- Pairwise correlation computed rolling 60-day
- Cluster of 3+ positions > 0.6 avg correlation → "crowded"
- Book avg > 0.4 → deleverage alert

---

## 13. Data Architecture

### 13.1 Data Platform (Already Built)

```
src/data_platform/
├── universe.py       # Ticker universe + hedge resolution
├── prices.py         # yfinance → SQLite, pair ratios, returns
├── technicals.py     # MA, RSI, MACD, KST, ADX, ATR, Bollinger, Fibonacci
├── valuations.py     # P/E, EV/EBITDA, peer comps
├── macro_data.py     # 45+ FRED indicators
├── carry.py          # SOFR, daily carry math
├── trailing_stop.py  # Per-position trailing stop engine
├── factor_betas.py   # 9-factor beta computation
├── circuit_breaker.py# 4%/6% drawdown monitor
├── sizing.py         # Conviction-based sizing + HC tier
├── book.py           # Portfolio state, mark-to-market, blotter
├── news.py           # Headlines, earnings, event detection
└── cli.py            # JSON CLI for OpenClaw shell access
```

### 13.2 CLI Access (How Agents Call Tools)
```bash
cd src && python -m data_platform.cli <command> <subcommand> [options]
```
All output is JSON to stdout — directly parseable by OpenClaw agent sessions.

### 13.3 Data Storage
```
data/
├── prices.db    # SQLite: EOD OHLCV for all POC tickers
├── carry.db     # SQLite: SOFR rates
└── macro.db     # SQLite: FRED macro indicator cache
```

---

## 14. State Management & Persistence

### 14.1 Book State (JSON file)

```json
{
  "nav": 10000000,
  "initial_nav": 10000000,
  "cash_pct": 0.84,
  "positions": [
    {
      "ticker": "XOM",
      "direction": "long",
      "hedge_ticker": "RSPG",
      "hedge_direction": "short",
      "entry_price": 105.0,
      "hedge_entry_price": 88.5,
      "size_pct_nav": 0.04,
      "conviction": 8,
      "pair_ratio": 1.1864,
      "trailing_stop_level": 103.25,
      "pnl_pct": 0.018,
      "status": "active"
    }
  ],
  "trade_journal": []
}
```

Persisted to `memos/state/book.json` after each cycle. OpenClaw agents read this for current context.

### 14.2 Memo Persistence
All agent outputs (proposals, debates, scores, decisions, orders) persist as JSON files in the `memos/` directory tree. This IS the audit trail.

---

## 15. Orchestration & Scheduling

### 15.1 POC Orchestrator: `run_cycle.py`

A single Python script that invokes OpenClaw agents in sequence:

```python
#!/usr/bin/env python3
"""POC Orchestrator — runs one full pipeline cycle."""

# Phase 1: Data refresh
# Phase 2: Blind first pass (fund_energy + macro_commodities in parallel)
# Phase 3: Memo exchange debate (2-3 rounds)
# Phase 4: Technical scoring
# Phase 5: Risk gate (different model)
# Phase 6: PM decision
# Phase 7: Update book state + output blotter
```

### 15.2 Scheduling (POC)
- **Manual trigger:** `python run_cycle.py` — runs one full cycle
- **Optional cron:** Schedule daily at 17:00 ET for EOD cycle
- **No Asia/London clock in POC** — single daily cycle only

### 15.3 Agent Invocation Order

```
1. python -m data_platform.cli prices update --tickers XOM CVX COP EOG SLB MPC PSX VLO OXY DVN XLE RSPG RSP USO XOP GLD
2. openclaw run fund_energy (blind, writes proposal)
3. openclaw run macro_commodities (blind, writes proposal)
4. openclaw run fund_energy --debate (reads macro's proposal, responds)
5. openclaw run macro_commodities --debate (reads fund's proposal, responds)
6. [conviction check — scripted, not LLM]
7. openclaw run tech_equity (scores surviving proposals)
8. openclaw run risk_management (gates proposals — DIFFERENT MODEL)
9. openclaw run portfolio_manager (sizes approved trades)
10. Update book.json + print blotter
```

---

## 16. Delivery & Interaction Layer

### 16.1 POC Output
- **Console:** Formatted blotter printed after each cycle
- **File:** `memos/orders/` contains JSON trade orders
- **Optional:** Pipe to email via a simple sendmail script

### 16.2 Output Format
```
═══════════════════════════════════════════════
          DAILY CYCLE COMPLETE
═══════════════════════════════════════════════
Proposals generated: 2
Survived debate: 1
Risk approved: 1
Trade orders: 1

BOOK STATE:
NAV: $10,045,000  (+0.45%)
Positions: 2
Gross: 16%  Net: +4%

BLOTTER:
XOM/RSPG @ 1.1864  +1.8%  [8/10 S]  long 4.0%  trail@103.25
XLE/RSP @ 0.5452   +2.1%  [7/10 S]  long 3.0%  trail@87.50

NEW ORDER:
BUY COP / SHORT RSPG  |  4% NAV ($400K/leg)
Entry: market  |  Stop: trail 2.5%  |  Target: +5% PM review
Thesis: [summary from proposal]
═══════════════════════════════════════════════
```

---

## 17. Infrastructure & Deployment

### 17.1 Hardware
- MacBook Pro (M-series, 16GB+ RAM, 256GB+ storage)
- No external services required beyond LLM API

### 17.2 Software Stack

```yaml
runtime:
  language: Python 3.9+
  agent_manager: OpenClaw (installed locally)
  
llm:
  primary: Anthropic Claude Sonnet (research agents)
  risk_gate: OpenAI GPT-4o (different model family per spec)
  cost: ~$0.50-2.00 per full cycle (5 agents × 2-4 calls each)

data_layer:
  database: SQLite (prices.db, carry.db, macro.db)
  state: JSON files (book.json)
  communication: filesystem (memos/ directory)

tools:
  data_platform CLI: JSON output to stdout
  yfinance: free price/fundamental data
  FRED: free macro data (with API key)
```

### 17.3 Directory Structure

```
AgenticTradingResearch/
├── src/data_platform/       # 12 modules + CLI (already built)
├── data/                    # SQLite databases
├── openclaw/
│   ├── mandates/            # Agent markdown mandates
│   │   ├── fund_energy.md
│   │   ├── macro_commodities.md
│   │   ├── tech_equity.md
│   │   ├── risk_management.md
│   │   └── portfolio_manager.md
│   └── tools/               # Tool definitions for OpenClaw
│       └── data_platform.json
├── memos/                   # Agent communication (per-cycle)
│   ├── proposals/
│   ├── debate/
│   ├── scores/
│   ├── risk/
│   ├── orders/
│   └── state/
│       └── book.json
├── run_cycle.py             # Orchestrator script
└── specs/                   # Design docs
```

---

## 18. Security & Access

### 18.1 POC Security Model
- All local (no network exposure)
- API keys in environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FRED_API_KEY`)
- OpenClaw permissions: shell access scoped to project directory only
- No auto-execution — output is advisory text/JSON

### 18.2 OpenClaw Permissions (Restricted)
```yaml
openclaw_permissions:
  shell_access: true (scoped to project dir)
  file_read: true (memos/, data/, src/)
  file_write: true (memos/ only)
  network: true (LLM API calls + yfinance)
  system_commands: false (no sudo, no installs)
```

---

## 19. Monitoring & Observability

### 19.1 POC Monitoring (Simple)
- Log each agent invocation (start time, end time, tokens used, output file)
- Track proposals generated / survived / approved / rejected per cycle
- Track LLM cost per cycle
- Write cycle summary to `memos/logs/cycle_<date>.json`

---

## 20. Performance & Scaling

### 20.1 POC Performance
- Full cycle time: 3-5 minutes (5 agents × 30-60 seconds each)
- LLM calls per cycle: 15-25 (including debate rounds)
- Data refresh: 10-20 seconds (17 tickers, incremental)

### 20.2 Scaling to Production
- Add more agents (11 fundamental + 6 macro + 2 technical) → OpenClaw handles session management
- Swap SQLite → PostgreSQL
- Add Redis for message bus
- Add scheduler (APScheduler or cron) for clock-driven triggers
- Expand universe in `universe.py`

---

## 21. Failure Modes & Recovery

### 21.1 POC Failure Handling
- LLM API failure → retry once, then skip agent for this cycle
- Invalid agent output (malformed JSON) → retry with error feedback
- 3 consecutive failures → disable agent, alert to console
- Data fetch failure → flag as "stale_data" in proposal, risk applies wider margins

### 21.2 Recovery
- Re-run `python run_cycle.py` — idempotent (won't duplicate positions)
- Book state persists in `book.json` — survives crashes

---

## 22. Cost Model

### 22.1 POC Monthly Cost

```yaml
llm_api:
  # 1 cycle/day × 20 calls/cycle × 30 days = 600 calls/month
  # Mix: 80% Sonnet ($0.015/call) + 20% GPT-4o ($0.03/call)
  # = 600 × $0.018 avg = ~$11/month
  estimated_monthly: $10 - $20

data:
  yfinance: $0 (free)
  FRED: $0 (free with API key)
  NewsAPI: $0 (free tier, 100 req/day)

infrastructure:
  MacBook Pro: $0 (already owned)
  OpenClaw: $0 (open source)

total_monthly: $10 - $20
```

---

## 23. Development Phases

### Phase 1: Setup (Day 1)
- Install OpenClaw on MacBook Pro
- Backfill price data for POC universe
- Create directory structure (memos/, openclaw/, etc.)
- Verify CLI tools work end-to-end

### Phase 2: Agent Mandates (Day 2-3)
- Write 5 mandate markdown files
- Define tool access per agent
- Test each agent in isolation (single invocation, check JSON output)

### Phase 3: Debate Engine (Day 4-5)
- Build orchestrator script (run_cycle.py)
- Implement blind first pass → memo exchange → conviction check
- Test 2-agent debate produces meaningful challenge/response

### Phase 4: Risk + PM Pipeline (Day 6-7)
- Wire risk gate (different model, reads proposals + scores)
- Wire PM agent (sizes trades, writes orders)
- Test full pipeline end-to-end

### Phase 5: Book State + Output (Day 8-9)
- Implement book.json persistence
- Mark-to-market on each cycle
- Trailing stop updates
- Formatted blotter output

### Phase 6: First Live Cycle (Day 10)
- Run full cycle with real (current) market data
- Evaluate output quality
- Iterate on prompts based on results

---

## Appendix A: POC vs. Production Differences

| Dimension | POC | Production |
|-----------|-----|-----------|
| Universe | 10 energy names + 6 ETFs | Full S&P 500 + 20 country + commodities |
| Agents | 5 | 21 |
| Agent manager | OpenClaw (local) | OpenClaw (Mac Mini, always-on) |
| LLM | Claude Sonnet + GPT-4o | 5-tier model routing |
| Scheduling | Manual trigger | Clock + event-driven |
| NAV | $10mm paper | $650mm paper |
| Debate | 2-3 rounds, file-based | Isolated sessions, memo exchange (same pattern) |
| Data | yfinance + FRED (free) | Bloomberg/Polygon + FactSet + FRED |
| State | JSON files | PostgreSQL + Redis |
| Output | Console + JSON files | Email + dashboard + mobile push |
| Cost | ~$15/month | ~$750/month |

---

*End of POC Design Document*
