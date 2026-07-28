# Agentic AI Trading System — Framework Specification (POC)

**Version:** 0.1 (Proof of Concept)  
**Date:** 2026-07-26  
**Scope:** Architecture design, agent contracts, data flow, and a minimal viable slice for validation — not a production build.

---

## 1. Objective & POC Scope

### Full Vision
A multi-agent system that continuously screens a defined equity/ETF/commodity universe, generates hedged long/short trade recommendations through a structured debate and approval pipeline, and delivers those recommendations for discretionary human review.

### POC Boundary
The POC validates the **agent communication framework, debate protocol, and risk-gating pipeline** using:
- A reduced universe (e.g., one sector — Energy — plus its hedge instruments)
- Stub data sources (cached/sample market data rather than live feeds)
- Single instances of each agent type (1 fundamental, 1 macro, 1 technical, 1 risk, 1 PM)
- Local execution on a personal device
- Console/file-based output (no email/UI integration yet)

Success criteria: the pipeline produces a structured, hedged trade recommendation that passes through debate → technical scoring → risk approval → PM sizing, with an auditable trail.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│  (Event loop / scheduler — triggers agent cycles, routes msgs)  │
└──────────┬──────────────────────────────────┬───────────────────┘
           │                                  │
     ┌─────▼─────┐                    ┌──────▼──────┐
     │  MESSAGE   │                    │   STATE     │
     │    BUS     │                    │   STORE     │
     │ (pub/sub)  │                    │ (positions, │
     └─────┬──────┘                    │  book, P&L) │
           │                           └─────────────┘
   ┌───────┼───────────────────────────────────┐
   │       │       │        │         │        │
┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼───┐ ┌───▼──┐ ┌──▼──┐
│FUND │ │MACRO│ │TECH │ │ RISK │ │  PM  │ │DATA │
│AGENT│ │AGENT│ │AGENT│ │AGENT │ │AGENT │ │SVC  │
└─────┘ └─────┘ └─────┘ └──────┘ └──────┘ └─────┘
```

### Components

| Component | Responsibility |
|-----------|---------------|
| **Orchestrator** | Schedules agent runs (daily/weekly/on-demand), routes messages between agents, enforces the debate/approval sequence. |
| **Message Bus** | Async pub/sub channel for trade proposals, debates, scores, approvals. Allows agents to publish and subscribe to typed events. |
| **State Store** | Persists current book (positions, P&L, factor exposures), trade history, and agent memory/context. |
| **Data Service** | Abstraction layer over market data (prices, fundamentals, macro indicators). POC uses cached/sample data; production swaps in live APIs. |

---

## 3. Agent Taxonomy & Contracts

### 3.1 Fundamental Agents (×11 in production; ×1 in POC)

**Role:** Bottom-up sector specialist. Builds financial models, identifies variant perception vs. consensus.

**Inputs:** Sector constituents, financials (revenue, margins, FCF, leverage), peer multiples, earnings estimates, news.

**Outputs:** `TradeProposal` — ticker, direction (long/short), thesis, conviction score (1–10), target price, catalyst timeline.

**Sector-Specific KPIs (examples):**
- Energy: production, reserves, breakevens, rig counts
- Financials: NIM, credit quality, capital ratios, loan growth
- Technology: ARR, net revenue retention, R&D intensity
- Industrials: backlog, book-to-bill, capacity utilization

**Constraints:** Every single-name trade must include the equal-weight sector ETF hedge (opposite direction).

---

### 3.2 Macro Agents (×6 in production; ×1 in POC)

**Role:** Top-down regional/product specialist. Forms a macro view and maps it to country ETF or commodity expressions.

**Regions:** LatAm, CEEMEA, Asia, North America, Western Europe, Commodities.

**Inputs:** GDP, PMIs, labor data, inflation, central bank policy, fiscal/debt metrics, BoP, FX valuation, political risk, commodity S/D balances.

**Outputs:** `TradeProposal` — ETF/commodity ticker, direction, macro thesis, conviction, target.

**Region-Specific Drivers (examples):**
- LatAm: fiscal slippage, commodity terms of trade
- CEEMEA: energy dependence, geopolitics
- Asia: China credit impulse, trade cycle
- Commodities: S/D balance, inventories, cost curve, futures curve shape

**Constraints:** DM ideas hedged with DM ETF or ACWI; EM ideas hedged with EEM or ACWI.

---

### 3.3 Technical Agent(s)

**Role:** Evaluate proposals on technicals; surface purely technical setups.

**Inputs:** Price series, volume, options data, moving averages, momentum indicators.

**Outputs:** `TechnicalScore` — score (1–10), key levels (support/resistance/Fibonacci), trailing stop suggestion, take-profit level, CTA flow context.

**Methods:** Price momentum, MA crossovers, KST, RSI, volume profile, options skew, mean-reversion signals.

**Constraints:** Purely technical ideas must be debated with fundamental/macro agents before PM review.

---

### 3.4 Risk Management Agent

**Role:** Gate-keep all proposals against portfolio-level risk limits.

**Inputs:** Current book state, proposed trade, factor beta exposures, correlation matrix.

**Outputs:** `RiskDecision` — approved/rejected/modify, rationale, suggested sizing adjustment, updated factor exposure projection.

**Rules (hard constraints):**
- No single factor beta > ±0.6 (DXY, SPX, USGG10Yr, VIX, Growth/Value, CL1, Large/Small, CDX HY 5Y, XAU)
- Position stop-loss: 2–3%
- Position gain target: 5%
- Downside vol budget: 6% annualized
- Leverage adjusts dynamically: higher when winning + low correlation; lower when losing or crowded

---

### 3.5 Portfolio Management Agent

**Role:** Final decision-maker. Sizes positions, sets stops, manages the book, delivers recommendations.

**Inputs:** Risk-approved proposals with technical scores, current book, P&L, market regime context.

**Outputs:** `TradeOrder` — final sizing (% of NAV), entry level, stop-loss, take-profit, hedge leg details, rationale.

**Behavior:** Operates like a macro PM — synthesizes all inputs, optimizes for 12–15% return / 6% downside vol, decides whether to add or pass.

---

## 4. Message Types & Debate Protocol

### 4.1 Core Message Types

```python
@dataclass
class TradeProposal:
    id: str
    agent_id: str
    ticker: str
    direction: Literal["long", "short"]
    hedge_ticker: str
    hedge_direction: Literal["long", "short"]
    thesis: str
    conviction: int  # 1-10
    target_price: float
    stop_loss_pct: float
    catalyst_timeline: str
    timestamp: datetime

@dataclass
class DebateMessage:
    proposal_id: str
    agent_id: str
    stance: Literal["support", "challenge", "neutral"]
    argument: str
    revised_conviction: Optional[int]

@dataclass
class TechnicalScore:
    proposal_id: str
    score: int  # 1-10
    support_level: float
    resistance_level: float
    suggested_stop: float
    suggested_target: float
    momentum_regime: str

@dataclass
class RiskDecision:
    proposal_id: str
    decision: Literal["approved", "rejected", "modify"]
    rationale: str
    max_position_size_pct: Optional[float]
    projected_factor_impact: dict

@dataclass
class TradeOrder:
    proposal_id: str
    execute: bool
    size_pct_nav: float
    entry_level: float
    stop_loss: float
    take_profit: float
    hedge_size_pct_nav: float
    pm_rationale: str
```

### 4.2 Pipeline Sequence

```
1. IDEA GENERATION
   Fundamental/Macro agent publishes TradeProposal
        │
2. DEBATE (2–3 rounds max)
   Other fundamental/macro agents publish DebateMessages
   Originator may revise conviction or withdraw
        │
3. TECHNICAL SCORING
   Technical agent publishes TechnicalScore
   (If technical agent originated, debate happens here instead)
        │
4. RISK GATE
   Risk agent evaluates against book state → RiskDecision
   If "modify": feeds back to PM with constraints
   If "rejected": proposal dies (logged)
        │
5. PM DECISION
   PM agent sizes and finalizes → TradeOrder
   Order delivered to output channel (file/email/UI)
```

### 4.3 Debate Rules
- Maximum 3 rounds of back-and-forth per proposal
- If conviction drops below 5 after debate, proposal is auto-withdrawn
- Agents must cite data/evidence in debate messages (no unsupported opinions)
- Tie-breaking: PM agent has final discretion

---

## 5. Universe Definition

### POC Universe (Energy sector slice)

| Category | Tickers |
|----------|---------|
| Single names | XOM, CVX, COP, EOG, SLB, MPC, PSX, VLO, OXY, DVN |
| Sector ETF | XLE |
| Equal-weight hedge | RSPG |
| Broad hedge | RSP |
| Commodity | CL1 (WTI crude proxy via USO or similar) |

### Production Universe (full)

- **Equities:** All S&P 500 constituents
- **Sector ETFs:** XLE, XLF, XLK, XLV, XLY, XLP, XLI, XLB, XLRE, XLC, XLU
- **Country ETFs:** 20 predefined MSCI country ETFs (EWJ, EWZ, EWG, FXI, EWY, EWT, EWA, EWC, EWU, EWH, EWS, EWM, EWW, EWI, EWP, EWQ, EWL, EWD, EWN, INDA)
- **Commodities:** GLD, SLV, GDX, SIL, COPX, AA, USO, XOP
- **Hedge instruments:** RSP, RSPG, RSPT, RSPF, etc. (equal-weight sector ETFs), EEM, ACWI, EFA

---

## 6. Data Layer (POC)

### 6.1 Sources (stubbed for POC)

| Data Type | POC Source | Production Source |
|-----------|-----------|-------------------|
| Price/volume | CSV snapshots / yfinance cache | Bloomberg/Refinitiv API |
| Fundamentals | Static JSON per ticker | FactSet / S&P Capital IQ |
| Macro indicators | Hardcoded scenario data | FRED, IMF, central bank APIs |
| Options/vol | Sample skew data | CBOE / broker API |
| News/sentiment | Sample headlines | NewsAPI, RSS, Twitter/X |

### 6.2 Data Service Interface

```python
class DataService(Protocol):
    def get_price_history(self, ticker: str, lookback_days: int) -> pd.DataFrame: ...
    def get_fundamentals(self, ticker: str) -> dict: ...
    def get_macro_indicators(self, region: str) -> dict: ...
    def get_options_data(self, ticker: str) -> dict: ...
    def get_news(self, ticker: str, days: int) -> list[str]: ...
    def get_factor_exposures(self, portfolio: dict) -> dict: ...
```

---

## 7. State Management

### 7.1 Book State

```python
@dataclass
class Position:
    ticker: str
    direction: Literal["long", "short"]
    size_pct_nav: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    hedge_ticker: str
    hedge_direction: Literal["long", "short"]
    hedge_size_pct_nav: float
    entry_date: date
    originating_agent: str
    proposal_id: str

@dataclass
class BookState:
    positions: list[Position]
    cash_pct: float
    total_nav: float
    inception_date: date
    realized_pnl: float
    unrealized_pnl: float
    factor_betas: dict[str, float]  # factor_name -> beta
    leverage_gross: float
    leverage_net: float
```

### 7.2 Persistence
- POC: SQLite file + JSON logs
- Production: PostgreSQL + time-series DB for price/factor history

---

## 8. Agent Implementation (POC Approach)

Each agent is an LLM-backed reasoning loop with:

```
┌─────────────────────────────┐
│         AGENT SHELL         │
├─────────────────────────────┤
│ System Prompt (role, rules) │
│ Context Window              │
│   - Book state              │
│   - Relevant data           │
│   - Recent messages         │
│ Tool Access                 │
│   - DataService calls       │
│   - Message publishing      │
│   - State queries           │
│ Output Parser               │
│   - Structured JSON output  │
│   - Validation layer        │
└─────────────────────────────┘
```

### Key Design Decisions

1. **LLM backbone:** Each agent wraps a prompted LLM call (Claude/GPT-4 class) with structured output parsing.
2. **Memory:** Short-term via conversation context; long-term via persisted trade history and agent-specific notes in the state store.
3. **Tool use:** Agents call the DataService and StateStore via function-calling / tool-use patterns.
4. **Determinism:** All agent outputs are validated against schemas; malformed outputs trigger a retry with error feedback.
5. **Auditability:** Every message, decision, and state change is logged with timestamps and agent IDs.

---

## 9. Hedging Rules (Codified)

| Trade Level | Long Leg | Hedge (Short) Leg |
|-------------|----------|-------------------|
| Single name (sector) | Long TICKER | Short equal-weight sector ETF (e.g., RSPG) |
| Single name (sector) | Short TICKER | Long equal-weight sector ETF (e.g., RSPG) |
| Sector ETF | Long XLE | Short RSP |
| Sector ETF | Short XLE | Long RSP |
| Country ETF (DM) | Long EWJ | Short EFA or ACWI |
| Country ETF (EM) | Long EWZ | Short EEM or ACWI |
| Commodity | Long GLD | Short broad commodity or ACWI (PM discretion) |

**Rule:** No unhedged directional exposure. Every position has an opposite-direction pair. The Risk agent enforces this structurally.

---

## 10. Risk Limits (Codified)

```yaml
risk_limits:
  target_return_annual: 0.12 - 0.15
  max_downside_vol: 0.06
  position_stop_loss: 0.02 - 0.03
  position_gain_target: 0.05
  max_factor_beta: 0.6   # absolute value, per factor
  factors_tracked:
    - DXY
    - SPX
    - USGG10Yr
    - VIX
    - Growth/Value
    - CL1
    - Large/Small
    - CDX HY 5Y
    - XAU
  leverage:
    dynamic: true
    increase_when: "positive P&L AND low inter-position correlation"
    decrease_when: "drawdown OR high correlation"
```

---

## 11. Technology Stack (POC)

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.11+ | Ecosystem for finance/ML, fast prototyping |
| LLM interface | LangChain or raw API calls (OpenAI/Anthropic SDK) | Structured output, tool use |
| Orchestration | Custom event loop (asyncio) | Simple, no infra overhead for POC |
| Message bus | In-process queue (asyncio.Queue) | No external deps; swap for Redis/Kafka in prod |
| State store | SQLite + JSON files | Zero-config, portable |
| Data | yfinance + static fixtures | Free, no API keys for POC |
| Output | Console + markdown file | Human-readable trade blotter |

---

## 12. POC Deliverables

1. **Orchestrator** — event loop that cycles agents on a trigger (manual or cron)
2. **Agent shells** — 5 agent classes (Fundamental, Macro, Technical, Risk, PM) with system prompts and structured I/O
3. **Message bus** — in-process pub/sub with typed events
4. **Data service** — interface + yfinance/static implementation
5. **State store** — SQLite schema for book state, trade log, message history
6. **Debate engine** — manages multi-round back-and-forth, enforces round limits
7. **Risk gate** — validates proposals against factor limits and position constraints
8. **Trade blotter output** — formatted recommendation with full audit trail
9. **Sample run** — end-to-end demo producing 1–2 trade recommendations from the Energy universe

---

## 13. What's Out of Scope for POC

- Live market data feeds
- Email/Slack/UI delivery
- Full 500-name universe
- All 11 fundamental + 6 macro agents running simultaneously
- Backtesting engine
- Real P&L tracking
- Authentication / multi-user access
- Deployment infrastructure (containers, cloud)
- Options strategy recommendations
- Intraday execution logic

---

## 14. Migration Path: POC → Production

| Dimension | POC | Production |
|-----------|-----|-----------|
| Universe | 10 energy names | Full S&P 500 + ETFs + commodities |
| Agents | 5 total | 11 fundamental + 6 macro + 2 technical + 1 risk + 1 PM = 21 |
| Data | Static/cached | Live Bloomberg/Refinitiv/FRED |
| Message bus | In-process queue | Redis Streams or Kafka |
| State | SQLite | PostgreSQL + TimescaleDB |
| Scheduling | Manual trigger | Cron / event-driven (market open, data release) |
| Output | Console/file | Email + web dashboard |
| Compute | Single machine | Containerized (Docker) on personal server or cloud |
| Monitoring | Log files | Structured logging + alerting |

---

## 15. Open Questions

1. **LLM provider:** Claude vs. GPT-4 vs. mixture? Cost/latency/quality tradeoffs for 21 agents running daily.
2. **Agent memory:** How much historical context to feed per cycle? Summarized vs. raw?
3. **Debate depth:** Is 3 rounds sufficient, or do some ideas need deeper adversarial testing?
4. **Factor beta calculation:** Use rolling 12-month regression against each factor — do we compute in-house or pull from a provider?
5. **Position sizing model:** Fixed fractional, Kelly, or risk-parity across positions?
6. **Interaction model:** How do you want to interact while at the desk? Read-only dashboard? Ability to override/veto?
7. **Frequency:** Daily full cycle vs. continuous monitoring with event-driven triggers?

---

## 16. Next Steps

1. **Validate this spec** — confirm architecture, agent contracts, and risk rules are correct.
2. **Build agent prompts** — draft system prompts for each agent role with sector/region specificity.
3. **Implement data service** — wire up yfinance + static fixtures for Energy universe.
4. **Build orchestrator + message bus** — minimal event loop with typed message routing.
5. **Implement debate engine** — multi-round protocol with conviction tracking.
6. **End-to-end demo** — run the pipeline and produce a sample trade recommendation.
