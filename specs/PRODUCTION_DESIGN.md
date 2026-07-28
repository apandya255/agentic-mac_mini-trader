# Agentic AI Trading System — Production Design Document

**Version:** 1.0  
**Date:** 2026-07-26  
**Classification:** Internal  
**Scope:** Full production architecture for a multi-agent long/short equity, macro, and commodity trading system.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Objectives & Constraints](#2-system-objectives--constraints)
3. [Universe Specification](#3-universe-specification)
4. [Agent Architecture](#4-agent-architecture)
5. [Fundamental Agents (×11)](#5-fundamental-agents)
6. [Macro Agents (×6)](#6-macro-agents)
7. [Technical Agents (×2)](#7-technical-agents)
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

This document specifies the production architecture for a multi-agent AI trading system that continuously screens equities, sector ETFs, country ETFs, and commodities to generate hedged long/short trade recommendations. The system employs 21 specialized agents — 11 fundamental sector analysts, 6 macro regional/product analysts, 2 technical analysts, 1 risk manager, and 1 portfolio manager — operating within a structured debate and approval pipeline. All recommendations are delivered for discretionary human evaluation; the system does not auto-execute.

The system runs on a personal device outside of any firm ecosystem and provides a secure interface for interaction during market hours.

---

## 2. System Objectives & Constraints

### Performance Targets
- Annualized return: 12–15%+
- Downside volatility: ≤6% annualized
- Position stop-loss: 2–3% per position
- Position gain target: 5% per position
- Sharpe ratio implied: ≥2.0

### Structural Constraints
- Every position must be hedged (no naked directional exposure)
- Combined book factor beta: ≤ ±0.6 to any single factor
- Factors tracked: DXY, SPX, USGG10Yr, VIX, Growth/Value, CL1, Large/Small cap, CDX HY 5Y, XAU
- Dynamic leverage: increases when P&L positive and correlation low; decreases in drawdowns or crowding
- Agents may hold cash (no forced investment)

### Operational Constraints
- Runs on personal hardware (Mac Studio / high-end laptop)
- Must be accessible (read-only interaction) from a work desk without touching firm systems
- No auto-execution — all trades are discretionary
- Full audit trail for every recommendation

---

## 3. Universe Specification

### 3.1 Equities
All constituents of the S&P 500 (approximately 503 securities), grouped by GICS sector:

| GICS Sector | # Names | Sector ETF | Equal-Weight Hedge ETF |
|-------------|---------|------------|------------------------|
| Energy | ~23 | XLE | RSPG |
| Materials | ~28 | XLB | RSPM (or custom basket) |
| Industrials | ~78 | XLI | RSPI |
| Consumer Discretionary | ~53 | XLY | RSPD |
| Consumer Staples | ~38 | XLP | RSPS |
| Health Care | ~64 | XLV | RSPH |
| Financials | ~72 | XLF | RSPF |
| Information Technology | ~68 | XLK | RSPT |
| Communication Services | ~22 | XLC | RSPC (or custom) |
| Utilities | ~31 | XLU | RSPU (or custom) |
| Real Estate | ~31 | XLRE | RSPR (or custom) |

### 3.2 Country ETFs (20 predefined MSCI)

**Developed Markets:**
EWJ (Japan), EWG (Germany), EWU (UK), EWA (Australia), EWC (Canada), EWH (Hong Kong), EWS (Singapore), EWL (Switzerland), EWD (Sweden), EWN (Netherlands), EWI (Italy), EWP (Spain), EWQ (France)

**Emerging Markets:**
EWZ (Brazil), FXI (China), EWY (South Korea), EWT (Taiwan), EWW (Mexico), EWM (Malaysia), INDA (India)

**Hedge Instruments:**
- DM ideas → short/long EFA (MSCI EAFE) or ACWI
- EM ideas → short/long EEM or ACWI

### 3.3 Commodities & Miners

| Asset | Primary Vehicle | Miner/Producer ETF |
|-------|----------------|-------------------|
| Gold | GLD | GDX |
| Silver | SLV | SIL |
| Copper | COPX | COPX (self-referencing) |
| Aluminum | AA (Alcoa as proxy) | — |
| Oil & Gas | USO / CL1 futures proxy | XOP |

### 3.4 Broad Hedge Instruments
- RSP (equal-weight S&P 500) — hedge for sector ETF level trades
- EFA / EEM / ACWI — hedges for country ETF trades
- Sector equal-weight ETFs — hedges for single-name trades

---

## 4. Agent Architecture

### 4.1 High-Level Topology

```
                    ┌──────────────────────────────┐
                    │        ORCHESTRATOR           │
                    │  (Scheduler + Pipeline Mgr)   │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐  ┌──────▼──────┐  ┌────────▼────────┐
    │   MESSAGE BUS      │  │ STATE STORE │  │  DATA PLATFORM  │
    │ (Redis Streams)    │  │ (Postgres)  │  │  (Market Data)  │
    └─────────┬─────────┘  └─────────────┘  └────────┬────────┘
              │                                       │
    ┌─────────┼───────────────────────────────────────┼──────┐
    │         │         AGENT POOL                    │      │
    │  ┌──────┴──────────────────────────────────┐   │      │
    │  │  FUNDAMENTAL AGENTS (×11)               │   │      │
    │  │  [Energy][Materials][Industrials]...     │◄──┤      │
    │  └─────────────────────────────────────────┘   │      │
    │  ┌─────────────────────────────────────────┐   │      │
    │  │  MACRO AGENTS (×6)                      │   │      │
    │  │  [LatAm][CEEMEA][Asia][NAm][WEur][Cmdty]│◄──┤      │
    │  └─────────────────────────────────────────┘   │      │
    │  ┌─────────────────────────────────────────┐   │      │
    │  │  TECHNICAL AGENTS (×2)                  │   │      │
    │  │  [Equity/ETF Technical][Commodity Tech] │◄──┤      │
    │  └─────────────────────────────────────────┘   │      │
    │  ┌─────────────────────────────────────────┐   │      │
    │  │  RISK MANAGEMENT AGENT (×1)             │◄──┤      │
    │  └─────────────────────────────────────────┘   │      │
    │  ┌─────────────────────────────────────────┐   │      │
    │  │  PORTFOLIO MANAGEMENT AGENT (×1)        │◄──┘      │
    │  └─────────────────────────────────────────┘          │
    └───────────────────────────────────────────────────────┘
```

### 4.2 Agent Base Architecture

Every agent shares a common runtime shell:

```python
class AgentRuntime:
    """Base runtime for all trading agents."""
    
    # Identity
    agent_id: str
    agent_type: AgentType  # fundamental | macro | technical | risk | pm
    specialization: str    # e.g., "energy", "latam", "equity_technical"
    
    # LLM Configuration
    model: str             # e.g., "claude-sonnet-4-20250514"
    temperature: float     # 0.3 for analytical, 0.5 for creative ideation
    max_tokens: int
    
    # Context Assembly
    system_prompt: str                    # Role-specific persona and rules
    long_term_memory: MemoryStore         # Persisted beliefs, past trades, lessons
    short_term_context: ContextWindow     # Current cycle data
    
    # Tool Access
    tools: list[Tool]                     # DataService, StateStore, MessageBus, Calculator
    
    # Output
    output_schema: type[BaseModel]        # Pydantic model for structured output
    validator: OutputValidator            # Schema + business rule validation
    
    # Execution
    async def run_cycle(self, trigger: CycleTrigger) -> AgentOutput: ...
    async def participate_in_debate(self, proposal: TradeProposal) -> DebateMessage: ...
    async def respond_to_query(self, query: str) -> str: ...
```

### 4.3 Memory Architecture

```
┌─────────────────────────────────────────┐
│            AGENT MEMORY                  │
├─────────────────────────────────────────┤
│                                         │
│  WORKING MEMORY (per-cycle)             │
│  - Current market data snapshot         │
│  - Active proposals under debate        │
│  - This cycle's observations            │
│                                         │
│  EPISODIC MEMORY (persistent)           │
│  - Past trade outcomes (win/loss/why)   │
│  - Debate transcripts (summarized)      │
│  - Lessons learned / belief updates     │
│                                         │
│  SEMANTIC MEMORY (reference)            │
│  - Sector/region knowledge base         │
│  - Model templates and frameworks       │
│  - Historical analogs                   │
│                                         │
│  BELIEFS (evolving)                     │
│  - Current macro/sector thesis          │
│  - Active watchlist with triggers       │
│  - Conviction levels per name           │
│                                         │
└─────────────────────────────────────────┘
```

Each agent maintains a belief state that persists across cycles and evolves as new data arrives. This prevents the system from "forgetting" a developing thesis between runs.

---

## 5. Fundamental Agents (×11)

### 5.1 Agent Roster

| Agent | Sector | Coverage | Key Vehicles |
|-------|--------|----------|--------------|
| fund_energy | Energy | ~23 names | XLE / RSPG |
| fund_materials | Materials | ~28 names | XLB / RSPM |
| fund_industrials | Industrials | ~78 names | XLI / RSPI |
| fund_cons_disc | Consumer Discretionary | ~53 names | XLY / RSPD |
| fund_cons_staples | Consumer Staples | ~38 names | XLP / RSPS |
| fund_healthcare | Health Care | ~64 names | XLV / RSPH |
| fund_financials | Financials | ~72 names | XLF / RSPF |
| fund_technology | Information Technology | ~68 names | XLK / RSPT |
| fund_comm_svcs | Communication Services | ~22 names | XLC / RSPC |
| fund_utilities | Utilities | ~31 names | XLU / RSPU |
| fund_real_estate | Real Estate | ~31 names | XLRE / RSPR |

### 5.2 Analytical Framework

Each fundamental agent operates as a long/short equity analyst with sector expertise:

**Core Process:**
1. **Model Building** — Revenue drivers, margin structure, FCF generation, balance sheet/leverage
2. **Valuation** — Sector-appropriate multiples (EV/EBITDA, P/E, P/FCF, P/B) + DCF where relevant, benchmarked vs. peers and own history
3. **Variant Perception** — Where do our estimates diverge from consensus? What's the market missing?
4. **Catalyst Identification** — What unlocks value? Earnings, M&A, restructuring, regulatory, cyclical turn
5. **Position Construction** — Long or short with appropriate hedge

**Long Candidates:** Mispriced quality, underappreciated catalysts, positive estimate revision trajectory, structural growth at reasonable price.

**Short Candidates:** Stretched valuations relative to fundamentals, deteriorating margins/cash flow, structural decline, negative estimate revision cycle, accounting red flags.

### 5.3 Sector-Specific KPIs

```yaml
energy:
  kpis: [production_growth, reserve_life, breakeven_price, rig_count_trend, 
         refining_margins, capex_discipline, shareholder_return_yield]
  drivers: [oil_price, gas_price, opec_policy, us_shale_activity, energy_transition]

financials:
  kpis: [NIM, credit_quality_NCOs, CET1_ratio, loan_growth, fee_income_mix,
         efficiency_ratio, tangible_book_value_growth, deposit_beta]
  drivers: [yield_curve, credit_cycle, regulatory_environment, loan_demand]

technology:
  kpis: [ARR_growth, net_revenue_retention, rule_of_40, R&D_intensity, 
         gross_margin_trend, FCF_conversion, TAM_penetration]
  drivers: [enterprise_spend_cycle, AI_adoption, cloud_migration, valuation_regime]

healthcare:
  kpis: [pipeline_value, patent_cliff_exposure, pricing_power, 
         organic_revenue_growth, M&A_capacity, regulatory_risk]
  drivers: [drug_approvals, pricing_legislation, demographics, innovation_cycle]

industrials:
  kpis: [backlog, book_to_bill, capacity_utilization, pricing_power,
         margin_expansion_runway, aftermarket_mix]
  drivers: [capex_cycle, infrastructure_spend, reshoring, supply_chain]

consumer_discretionary:
  kpis: [same_store_sales, market_share_trend, inventory_health, 
         digital_penetration, brand_strength, consumer_confidence_sensitivity]
  drivers: [consumer_spending, employment, housing, discretionary_wallet_share]

consumer_staples:
  kpis: [organic_growth, volume_vs_price_mix, private_label_share_threat,
         input_cost_exposure, dividend_sustainability]
  drivers: [inflation, consumer_trade_down, commodity_input_costs]

materials:
  kpis: [volume_growth, pricing_power, cost_curve_position, 
         capacity_additions, inventory_cycle_position]
  drivers: [global_PMI, china_construction, commodity_prices, trade_flows]

communication_services:
  kpis: [subscriber_growth, ARPU, content_ROI, advertising_revenue_growth,
         churn_rate, engagement_metrics]
  drivers: [ad_spend_cycle, streaming_competition, regulatory, AI_impact]

utilities:
  kpis: [rate_base_growth, allowed_ROE, regulatory_relationship, 
         renewable_transition_capex, dividend_coverage, wildfire_liability]
  drivers: [interest_rates, regulation, energy_transition, electrification]

real_estate:
  kpis: [FFO_growth, occupancy, lease_spreads, cap_rate_environment,
         development_pipeline, balance_sheet_leverage, NAV_discount]
  drivers: [interest_rates, remote_work, supply_pipeline, cap_rate_cycle]
```

### 5.4 Data Inputs per Agent Cycle

- Earnings estimates (consensus + revisions) for all coverage names
- Recent 10-Q/10-K filings (parsed key metrics)
- Price action (1D, 5D, 1M, 3M, 6M, 1Y returns)
- Peer group relative valuation matrix
- Sector news feed (last 48 hours)
- Management commentary / transcript highlights
- Short interest and institutional ownership changes
- Options activity (unusual volume, skew shifts)

### 5.5 Output: TradeProposal

```python
class FundamentalTradeProposal(BaseModel):
    proposal_id: str
    agent_id: str
    timestamp: datetime
    
    # Position
    ticker: str
    direction: Literal["long", "short"]
    hedge_ticker: str  # Equal-weight sector ETF
    hedge_direction: Literal["long", "short"]
    
    # Thesis
    thesis_summary: str  # 2-3 sentences
    thesis_detail: str   # Full write-up (500-1000 words)
    variant_perception: str  # Where we differ from consensus
    catalyst: str
    catalyst_timeline: str  # e.g., "2-4 weeks (earnings)", "3-6 months (restructuring)"
    
    # Valuation
    current_price: float
    target_price: float
    downside_price: float  # bear case
    implied_upside_pct: float
    primary_valuation_method: str
    valuation_detail: dict  # method-specific (multiples, DCF assumptions, etc.)
    
    # Conviction & Risk
    conviction: int  # 1-10
    confidence_interval: str  # "high", "medium", "low"
    key_risks: list[str]
    stop_loss_level: float
    
    # Context
    sector_view: str  # bullish/bearish/neutral on the sector overall
    relevant_peers: list[str]
    earnings_date: Optional[date]
```

---

## 6. Macro Agents (×6)

### 6.1 Agent Roster

| Agent | Region/Product | Coverage | Key Vehicles |
|-------|---------------|----------|--------------|
| macro_latam | Latin America | Brazil, Mexico, Chile, Colombia, Peru | EWZ, EWW |
| macro_ceemea | CEEMEA | Turkey, South Africa, Poland, Saudi, UAE, Egypt | Regional ETFs |
| macro_asia | Asia | China, Japan, Korea, Taiwan, India, ASEAN | FXI, EWJ, EWY, EWT, INDA |
| macro_north_america | North America | US, Canada | EWC, SPY/RSP |
| macro_western_europe | Western Europe | Eurozone, UK, Nordics, Switzerland | EWG, EWU, EWQ, EWI, EWP, EWL, EWD, EWN |
| macro_commodities | Commodities | Gold, Silver, Copper, Aluminum, Oil & Gas | GLD, SLV, COPX, AA, USO, GDX, SIL, XOP |

### 6.2 Analytical Framework

Each macro agent operates as a top-down macro analyst with regional/product expertise:

**Core Process:**
1. **Growth & Activity** — GDP trajectory, PMIs, labor market, leading indicators
2. **Inflation & Policy** — CPI/PPI path, central bank reaction function, rate expectations
3. **Fiscal & Debt** — Budget balance, debt sustainability, fiscal impulse, political will
4. **External Accounts** — Current account, BoP, reserves, capital flows, terms of trade
5. **Valuation & Flows** — FX valuation (REER), equity risk premium, foreign positioning
6. **Political & Geopolitical Risk** — Election cycles, policy uncertainty, conflict, sanctions
7. **Expression Selection** — Map the view into the cleanest tradeable instrument

### 6.3 Region-Specific Frameworks

```yaml
latam:
  key_drivers:
    - commodity_terms_of_trade
    - fiscal_slippage_and_reform
    - central_bank_credibility
    - political_cycle_and_populism
    - USD_strength_sensitivity
    - China_demand_channel
  primary_expressions: [EWZ, EWW]
  hedge_instruments: [EEM, ACWI]

ceemea:
  key_drivers:
    - energy_dependence_and_pricing
    - geopolitical_risk (Russia/Ukraine, Middle East)
    - EU_convergence_trade
    - current_account_vulnerability
    - central_bank_independence
    - sanctions_and_capital_controls
  primary_expressions: [regional ETFs, frontier access vehicles]
  hedge_instruments: [EEM, ACWI]

asia:
  key_drivers:
    - china_credit_impulse_and_property
    - global_trade_cycle_and_tariffs
    - semiconductor_cycle
    - JPY_and_BOJ_policy
    - india_structural_growth
    - ASEAN_supply_chain_shift
  primary_expressions: [FXI, EWJ, EWY, EWT, INDA]
  hedge_instruments: [EEM (for EM Asia), EFA (for Japan), ACWI]

north_america:
  key_drivers:
    - fed_policy_and_terminal_rate
    - us_fiscal_trajectory
    - labor_market_rebalancing
    - ai_productivity_impulse
    - canada_housing_and_resources
    - us_political_cycle
  primary_expressions: [EWC, sector_rotation_via_RSP]
  hedge_instruments: [ACWI, EFA]

western_europe:
  key_drivers:
    - ecb_policy_divergence
    - european_energy_security
    - fiscal_rules_and_reform
    - china_export_exposure
    - defense_spending_ramp
    - uk_post_brexit_trajectory
  primary_expressions: [EWG, EWU, EWQ, EWI, EWP, EWL, EWD, EWN]
  hedge_instruments: [EFA, ACWI]

commodities:
  key_drivers:
    - supply_demand_balance_per_commodity
    - inventory_levels_and_trends
    - cost_curve_and_marginal_producer
    - futures_curve_shape (contango_vs_backwardation)
    - USD_correlation
    - china_demand_impulse
    - energy_transition_demand_shift
    - geopolitical_supply_risk
  primary_expressions: [GLD, SLV, GDX, SIL, COPX, AA, USO, XOP]
  hedge_instruments: [ACWI, broad commodity index, or PM discretion]
```

### 6.4 Output: MacroTradeProposal

```python
class MacroTradeProposal(BaseModel):
    proposal_id: str
    agent_id: str
    timestamp: datetime
    
    # Position
    ticker: str  # Country ETF or commodity vehicle
    direction: Literal["long", "short"]
    hedge_ticker: str
    hedge_direction: Literal["long", "short"]
    
    # Thesis
    macro_regime: str  # e.g., "late cycle reflation", "EM divergence"
    thesis_summary: str
    thesis_detail: str
    key_data_points: list[str]  # Specific numbers/indicators supporting the view
    
    # Scenario Analysis
    base_case: str
    base_case_probability: float
    bull_case: str
    bull_case_probability: float
    bear_case: str
    bear_case_probability: float
    
    # Positioning
    target_return_pct: float
    stop_loss_pct: float
    conviction: int  # 1-10
    time_horizon: str  # "tactical (1-4 weeks)" | "medium-term (1-3 months)" | "structural (3-12 months)"
    
    # Risk Factors
    key_risks: list[str]
    risk_events_calendar: list[dict]  # {"date": ..., "event": ..., "impact": ...}
    correlation_to_existing_book: str
```

---

## 7. Technical Agents (×2)

### 7.1 Agent Roster

| Agent | Specialization | Coverage |
|-------|---------------|----------|
| tech_equity | Equities & ETFs | All S&P 500 names, sector ETFs, country ETFs |
| tech_commodity | Commodities | Gold, silver, copper, aluminum, oil & gas + miner ETFs |

### 7.2 Analytical Framework

**Signal Categories:**

```yaml
trend_following:
  - moving_averages: [20, 50, 100, 200 day SMA/EMA]
  - MA_crossovers: [golden_cross, death_cross, intermediate]
  - ADX_trend_strength: threshold > 25 for trending
  - price_channels: [Donchian, Keltner]

momentum:
  - RSI: [overbought > 70, oversold < 30, divergences]
  - MACD: [signal_crossover, histogram_momentum, divergences]
  - KST: [Know Sure Thing signal and crossovers]
  - rate_of_change: [12-period, 24-period]
  - relative_strength_vs_sector_and_market

mean_reversion:
  - bollinger_bands: [squeeze, expansion, band_touch]
  - z_score_from_moving_averages
  - RSI_extremes_with_reversal_confirmation
  - put_call_ratio_extremes
  - VIX_term_structure_extremes

volume_analysis:
  - OBV_trend
  - volume_price_confirmation
  - accumulation_distribution
  - unusual_volume_detection
  - dark_pool_prints (if available)

options_signals:
  - implied_vol_vs_realized_vol
  - skew_changes: [put_skew_steepening, call_skew]
  - unusual_options_activity
  - gamma_exposure_levels
  - max_pain_and_open_interest_clusters

flow_analysis:
  - CTA_positioning_and_trigger_levels
  - systematic_flow_estimates
  - ETF_creation_redemption
  - short_interest_changes
  - margin_debt_levels

key_levels:
  - fibonacci_retracements: [38.2%, 50%, 61.8%]
  - fibonacci_extensions: [127.2%, 161.8%]
  - pivot_points: [daily, weekly, monthly]
  - historical_support_resistance
  - volume_profile_POC (point of control)
  - VWAP_anchored
```

### 7.3 Output: TechnicalScore

```python
class TechnicalScore(BaseModel):
    proposal_id: str
    agent_id: str
    timestamp: datetime
    
    # Overall Assessment
    technical_score: int  # 1-10 (10 = strongest technical setup)
    trend_alignment: Literal["aligned", "neutral", "against"]
    momentum_regime: Literal["strong_trend", "weakening", "mean_reverting", "consolidating"]
    
    # Key Levels
    support_levels: list[float]  # ordered nearest to farthest
    resistance_levels: list[float]
    fibonacci_levels: dict[str, float]  # "38.2%": 145.50, etc.
    
    # Trade Management
    suggested_entry: float
    suggested_stop_loss: float  # technical stop (may differ from fundamental)
    suggested_take_profit: float
    trailing_stop_method: str  # e.g., "ATR-based 2x", "below 20-day MA"
    
    # Signals
    active_signals: list[dict]  # {"signal": "golden_cross", "strength": "strong", "date": ...}
    warning_signals: list[dict]  # conflicting or cautionary signals
    
    # Flow & Positioning
    cta_levels: dict  # {"buy_trigger": ..., "sell_trigger": ..., "current_position_estimate": ...}
    options_context: str
    volume_confirmation: bool
    
    # Timing
    timing_recommendation: Literal["now", "wait_for_pullback", "wait_for_breakout", "avoid"]
    timing_rationale: str
```

### 7.4 Technical Agent-Originated Ideas

When technical agents identify purely technical setups (breakouts, major divergences, extreme mean-reversion), they publish a `TechnicalTradeProposal` that must enter the debate pipeline:

```python
class TechnicalTradeProposal(BaseModel):
    """Technical-originated idea — requires fundamental/macro debate before PM review."""
    proposal_id: str
    agent_id: str
    ticker: str
    direction: Literal["long", "short"]
    hedge_ticker: str
    hedge_direction: Literal["long", "short"]
    
    technical_thesis: str
    setup_type: str  # "breakout", "mean_reversion", "divergence", "flow_driven"
    technical_score: int
    key_levels: dict
    
    # Must be filled after debate
    fundamental_endorsement: Optional[bool]
    macro_endorsement: Optional[bool]
    debate_summary: Optional[str]
```

---

## 8. Risk Management Agent

### 8.1 Role & Authority

The Risk Management Agent is the system's gatekeeper. No trade enters the book without its approval. It operates as a risk manager at an elite macro hedge fund — disciplined, quantitative, and empowered to reject or modify any proposal regardless of originating agent conviction.

### 8.2 Risk Framework

```yaml
position_level:
  max_position_size: 5% NAV (single name), 8% NAV (ETF)
  stop_loss: 2-3% of position notional
  gain_target: 5% of position notional
  max_sector_concentration: 25% gross (long + short per sector)
  max_single_name_concentration: 5% NAV
  correlation_limit: avoid >0.7 correlation between active positions

portfolio_level:
  factor_beta_limit: ±0.6 per factor
  factors:
    - DXY (US Dollar Index)
    - SPX (S&P 500)
    - USGG10Yr (US 10-Year Treasury Yield)
    - VIX (Volatility Index)
    - Growth_Value (Growth vs Value factor)
    - CL1 (Crude Oil front-month)
    - Large_Small (Large Cap vs Small Cap factor)
    - CDX_HY_5Y (High Yield Credit Spread)
    - XAU (Gold)
  
  max_gross_leverage: 3.0x (absolute ceiling)
  target_net_exposure: ±0.3 (near market neutral)
  max_drawdown_before_deleverage: 4% from peak
  max_downside_volatility: 6% annualized
  max_correlation_concentration: no more than 40% of risk in correlated cluster

leverage_management:
  regime_positive_low_corr:  # making money, positions uncorrelated
    leverage_range: 1.5x - 2.5x
  regime_positive_high_corr:  # making money but crowded
    leverage_range: 1.0x - 1.5x
  regime_negative_low_corr:  # losing but diversified
    leverage_range: 0.8x - 1.2x
  regime_negative_high_corr:  # losing and crowded — maximum caution
    leverage_range: 0.3x - 0.8x
```

### 8.3 Pre-Trade Risk Check Process

```python
class RiskAssessment(BaseModel):
    proposal_id: str
    timestamp: datetime
    
    # Decision
    decision: Literal["approved", "rejected", "approved_with_modifications"]
    rationale: str
    
    # Position-Level Checks
    position_size_ok: bool
    stop_loss_adequate: bool
    hedge_present_and_valid: bool
    sector_concentration_ok: bool
    correlation_to_existing_positions: float
    
    # Portfolio-Level Impact
    projected_factor_betas: dict[str, float]  # after adding this position
    factor_breach: bool  # would any factor exceed ±0.6?
    projected_gross_leverage: float
    projected_net_exposure: float
    projected_downside_vol: float
    
    # Modifications (if approved_with_modifications)
    max_allowed_size_pct: Optional[float]
    required_stop_loss: Optional[float]
    additional_hedge_required: Optional[str]
    timing_constraint: Optional[str]  # e.g., "wait for vol to subside"
    
    # Warnings
    risk_warnings: list[str]  # non-blocking concerns for PM awareness
```

### 8.4 Ongoing Position Monitoring

The risk agent also runs a monitoring cycle (separate from new-trade approval):

- **Stop-loss proximity alerts** — flag positions within 50bps of stop
- **Factor drift detection** — if book beta to any factor approaches ±0.5, alert PM
- **Correlation regime change** — if inter-position correlations spike, recommend deleveraging
- **Drawdown monitoring** — progressive deleverage triggers at 2%, 3%, 4% drawdown from peak
- **Liquidity monitoring** — flag positions where ADV suggests exit would take >2 days

---

## 9. Portfolio Management Agent

### 9.1 Role & Authority

The PM agent is the final decision-maker. It receives risk-approved proposals and determines:
1. Whether to execute the trade
2. Position sizing (within risk-approved limits)
3. Entry timing and execution approach
4. Stop-loss and take-profit calibration
5. Portfolio-level construction (how this trade fits the book)

It operates like a macro portfolio manager at an elite hedge fund — synthesizing fundamental, macro, technical, and risk inputs into a cohesive portfolio.

### 9.2 Decision Framework

```yaml
pm_decision_criteria:
  conviction_threshold: 6  # minimum post-debate conviction to consider
  technical_score_threshold: 5  # minimum to proceed
  
  sizing_model:
    base_size: 2% NAV  # starting point
    conviction_scalar: [0.5x at 6, 0.75x at 7, 1.0x at 8, 1.25x at 9, 1.5x at 10]
    technical_adjustment: [0.7x if tech_score < 6, 1.0x if 6-8, 1.2x if > 8]
    regime_adjustment: [0.5x in risk-off, 1.0x neutral, 1.3x risk-on]
    correlation_penalty: reduce by 20% for each existing position with >0.5 correlation
    
  portfolio_construction:
    max_ideas_per_cycle: 3  # don't add more than 3 new positions per day
    review_existing_first: true  # before adding new, check if existing need adjustment
    rebalance_frequency: weekly  # full book review
    
  exit_framework:
    stop_loss_hit: immediate exit
    target_reached: take 50% profit, trail remainder
    thesis_invalidated: exit regardless of P&L
    time_decay: review positions approaching catalyst deadline without move
    better_opportunity: may exit lower-conviction position to fund higher
```

### 9.3 Output: TradeOrder

```python
class TradeOrder(BaseModel):
    order_id: str
    proposal_id: str
    timestamp: datetime
    
    # Decision
    execute: bool
    pm_rationale: str  # Why yes/no, how it fits the book
    
    # Primary Leg
    ticker: str
    direction: Literal["long", "short"]
    size_pct_nav: float
    entry_approach: str  # "market", "limit at X", "scale in over 2 days"
    entry_price_limit: Optional[float]
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[str]
    
    # Hedge Leg
    hedge_ticker: str
    hedge_direction: Literal["long", "short"]
    hedge_size_pct_nav: float
    hedge_entry_approach: str
    
    # Portfolio Context
    portfolio_thesis: str  # how this trade fits the overall book narrative
    expected_holding_period: str
    review_date: date  # when to reassess if no movement
    
    # Delivery
    priority: Literal["urgent", "normal", "opportunistic"]
    notification_method: str  # "email", "dashboard", "sms"
```

---

## 10. Investment Process & Debate Protocol

### 10.1 Idea Generation Modes

```
MODE 1: CONTINUOUS SCREENING (Daily)
  All fundamental and macro agents scan their universe
  → Generate watchlist updates (evolving beliefs)
  → Surface new proposals when conviction threshold crossed

MODE 2: EVENT-DRIVEN (Real-time)
  Data event triggers agent activation:
  → Earnings release → relevant fundamental agent
  → Central bank decision → relevant macro agent
  → Technical breakout → technical agent
  → Geopolitical event → relevant macro agent(s)

MODE 3: SCHEDULED DEEP DIVE (Weekly)
  Full portfolio review cycle:
  → Every agent reassesses their active positions
  → PM agent runs portfolio-level optimization
  → Risk agent runs comprehensive factor/correlation check
```

### 10.2 Debate Protocol — Detailed Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DEBATE PROTOCOL                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  PHASE 1: PROPOSAL (originating agent)                               │
│  ├── Publish TradeProposal with full thesis                          │
│  └── Tag relevant counter-parties for debate                         │
│                                                                       │
│  PHASE 2: ADVERSARIAL REVIEW (2-3 rounds, max 48hr window)          │
│  ├── Round 1: Initial reactions from tagged agents                   │
│  │   ├── Sector peers challenge single-name thesis                   │
│  │   ├── Macro challenges sector/country timing                      │
│  │   └── Each response: support / challenge / neutral + evidence     │
│  ├── Round 2: Originator responds to challenges                      │
│  │   ├── Address each challenge with data/logic                      │
│  │   ├── Revise conviction if warranted                              │
│  │   └── May withdraw if challenges are fatal                        │
│  └── Round 3 (if needed): Final rebuttals                            │
│      ├── Challengers respond to originator's defense                 │
│      └── Final conviction assessment                                  │
│                                                                       │
│  PHASE 3: CONVICTION CHECK                                           │
│  ├── If conviction < 5 after debate → auto-withdraw                 │
│  ├── If conviction 5-6 → proceeds but flagged as lower priority     │
│  └── If conviction ≥ 7 → proceeds to technical scoring              │
│                                                                       │
│  PHASE 4: TECHNICAL SCORING                                          │
│  ├── Technical agent scores the setup (1-10)                         │
│  ├── Provides key levels, stops, targets                             │
│  └── If technical_score < 4 AND conviction < 8 → parked             │
│                                                                       │
│  PHASE 5: RISK GATE                                                  │
│  ├── Risk agent evaluates against full framework                     │
│  ├── Approved → proceeds to PM                                       │
│  ├── Modified → proceeds with constraints                            │
│  └── Rejected → logged with rationale, dead                          │
│                                                                       │
│  PHASE 6: PM DECISION                                                │
│  ├── PM sizes the trade within risk-approved limits                  │
│  ├── Sets final entry/stop/target parameters                         │
│  ├── Decides whether to execute now or wait                          │
│  └── Publishes TradeOrder → delivery channel                         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.3 Debate Rules (Enforced by Orchestrator)

1. **Evidence requirement:** Every challenge or support must cite specific data points, not vague assertions
2. **Time boxing:** Each round has a 4-hour window; agents that don't respond are counted as "neutral"
3. **Conflict of interest:** An agent cannot debate its own proposal (it can only respond to challenges)
4. **Escalation:** If fundamental and macro agents deadlock, PM agent has tie-breaking authority
5. **Fast-track:** Proposals with conviction ≥ 9 from a senior agent (one with positive track record) can skip to Phase 3
6. **Kill switch:** Any agent can flag "thesis-breaking event" to immediately halt a proposal

### 10.4 Technical Agent-Originated Ideas (Modified Flow)

When a technical agent surfaces an idea:
1. Technical agent publishes `TechnicalTradeProposal`
2. **Debate happens BEFORE technical scoring** (since the originator IS the technical agent)
3. Relevant fundamental agent must provide fundamental context (even if neutral)
4. Relevant macro agent must confirm no macro headwind
5. Both must endorse (or at least not reject) for the idea to proceed
6. Risk gate and PM decision proceed as normal

---

## 11. Hedging Framework

### 11.1 Mandatory Hedge Rules

Every position in the book must have an opposite-direction hedge leg. No exceptions.

```
┌─────────────────────────────────────────────────────────────────┐
│                   HEDGING DECISION TREE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Is the trade a SINGLE NAME in a GICS sector?                    │
│  ├── YES → Hedge with EQUAL-WEIGHT sector ETF                   │
│  │         Long AAPL → Short RSPT                                │
│  │         Short XOM → Long RSPG                                 │
│  │                                                                │
│  Is the trade a SECTOR ETF?                                      │
│  ├── YES → Hedge with RSP (equal-weight S&P 500)                │
│  │         Long XLE → Short RSP                                  │
│  │         Short XLF → Long RSP                                  │
│  │                                                                │
│  Is the trade a DEVELOPED MARKET country ETF?                    │
│  ├── YES → Hedge with EFA or ACWI (agent/PM discretion)         │
│  │         Long EWJ → Short EFA                                  │
│  │         Short EWG → Long ACWI                                 │
│  │                                                                │
│  Is the trade an EMERGING MARKET country ETF?                    │
│  ├── YES → Hedge with EEM or ACWI                               │
│  │         Long EWZ → Short EEM                                  │
│  │         Short FXI → Long ACWI                                 │
│  │                                                                │
│  Is the trade a COMMODITY or MINER?                              │
│  └── YES → Hedge determined by PM (typically broad market or    │
│            inverse commodity, or cross-commodity pair)            │
│            Long GLD → Short ACWI (or as PM sees fit)             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 11.2 Hedge Sizing

The default is **dollar-neutral** (equal notional on both legs). The PM agent may adjust the hedge ratio based on:
- Beta of the primary leg vs. the hedge instrument
- Volatility differential
- Desired residual exposure (e.g., 90% hedged if intentionally keeping some sector beta)

The risk agent validates that any non-dollar-neutral hedge ratio still keeps factor betas within limits.

### 11.3 Equal-Weight Sector ETF Mapping

| GICS Sector | Cap-Weight ETF | Equal-Weight Hedge ETF |
|-------------|---------------|------------------------|
| Energy | XLE | RSPG |
| Materials | XLB | RSPM |
| Industrials | XLI | RSPI |
| Consumer Discretionary | XLY | RSPD |
| Consumer Staples | XLP | RSPS |
| Health Care | XLV | RSPH |
| Financials | XLF | RSPF |
| Information Technology | XLK | RSPT |
| Communication Services | XLC | EWCO (or custom basket) |
| Utilities | XLU | RSPU |
| Real Estate | XLRE | EWRE (or custom basket) |

*Note: Where an official equal-weight ETF doesn't exist (e.g., Comm Services, Real Estate), the system uses the closest available equal-weight product or a custom-constructed basket.*

---

## 12. Risk Management Framework

### 12.1 Factor Beta Monitoring

The system computes rolling 12-month factor betas for the entire book against each tracked factor:

```python
TRACKED_FACTORS = {
    "DXY": "US Dollar Index",
    "SPX": "S&P 500 Total Return",
    "USGG10Yr": "US Generic Govt 10-Year Yield",
    "VIX": "CBOE Volatility Index",
    "Growth_Value": "Russell 1000 Growth / Value ratio",
    "CL1": "WTI Crude Oil Front Month",
    "Large_Small": "Russell 1000 / Russell 2000 ratio",
    "CDX_HY_5Y": "CDX North America High Yield 5-Year",
    "XAU": "Gold Spot Price"
}

# Computation: rolling 12-month OLS regression of daily book returns vs. each factor's daily returns
# Beta = slope coefficient
# Hard limit: |beta| ≤ 0.6 for EACH factor independently
```

### 12.2 Drawdown Management

```
Peak NAV tracking → progressive deleverage:

Drawdown from peak    Action
─────────────────     ──────────────────────────────────────────
0% - 2%               Normal operations
2% - 3%               Review lowest-conviction positions; reduce sizing 20%
3% - 4%               Mandatory deleverage to 50% of current gross; halt new additions
4%+                   Emergency deleverage to 30% of current gross; PM + Risk joint review
                      Only re-lever after 5 consecutive positive days
```

### 12.3 Position-Level Risk

```yaml
per_position:
  hard_stop_loss: 3% (absolute max — no exceptions)
  soft_stop_loss: 2% (triggers review — PM may override with documented rationale)
  gain_target: 5% (triggers partial profit-taking)
  max_holding_period_without_catalyst: 60 days (forces reassessment)
  
  concentration:
    max_single_position: 5% NAV (including hedge leg notional)
    max_sector_gross: 25% NAV
    max_country_gross: 15% NAV
    max_commodity_gross: 10% NAV
```

### 12.4 Correlation & Crowding

- Compute pairwise correlations of all active positions (rolling 60-day)
- If any cluster of 3+ positions shows average pairwise correlation > 0.6, flag as "crowded"
- Crowded clusters subject to aggregate size limit of 15% NAV gross
- If overall book average pairwise correlation > 0.4, trigger deleverage alert

---

## 13. Data Architecture

### 13.1 Data Platform Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA PLATFORM                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐            │
│  │ MARKET DATA │  │ FUNDAMENTAL  │  │  MACRO / ECON   │            │
│  │             │  │    DATA      │  │     DATA        │            │
│  ├─────────────┤  ├──────────────┤  ├─────────────────┤            │
│  │ Prices (EOD │  │ Financials   │  │ GDP, PMIs       │            │
│  │ + intraday) │  │ Estimates    │  │ CPI, Employment │            │
│  │ Volume      │  │ Revisions    │  │ Central Bank    │            │
│  │ Options     │  │ Filings      │  │ Fiscal Data     │            │
│  │ Short Int.  │  │ Transcripts  │  │ BoP, Reserves   │            │
│  │ Inst. Own.  │  │ M&A / Corp   │  │ PMI Components  │            │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘            │
│         │                │                    │                       │
│  ┌──────▼────────────────▼────────────────────▼────────┐            │
│  │              UNIFIED DATA SERVICE API                 │            │
│  │  (Normalizes, caches, versions, serves to agents)    │            │
│  └──────────────────────┬───────────────────────────────┘            │
│                         │                                             │
│  ┌──────────────────────▼───────────────────────────────┐            │
│  │              ALTERNATIVE DATA                          │            │
│  ├────────────────────────────────────────────────────────┤            │
│  │ News feeds (Reuters, Bloomberg, industry)              │            │
│  │ Earnings call transcripts (parsed + summarized)        │            │
│  │ Sell-side research summaries                           │            │
│  │ Social sentiment (Twitter/X, Reddit, StockTwits)       │            │
│  │ Satellite / web traffic / app download data            │            │
│  │ Government filings (13F, insider transactions)         │            │
│  └────────────────────────────────────────────────────────┘            │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 13.2 Data Sources — Production

| Category | Provider(s) | Frequency | Use |
|----------|-------------|-----------|-----|
| Prices & Volume | Bloomberg / Polygon / Alpaca | EOD + 15-min delayed | All agents |
| Options | CBOE / Polygon Options | EOD + intraday | Technical agent |
| Fundamentals | FactSet / S&P Capital IQ / SimFin | Quarterly + event-driven | Fundamental agents |
| Estimates & Revisions | FactSet / IBES | Daily | Fundamental agents |
| Filings (10-K/Q) | SEC EDGAR (parsed) | Event-driven | Fundamental agents |
| Transcripts | FactSet / Seeking Alpha | Event-driven | Fundamental agents |
| Macro Indicators | FRED / IMF / World Bank / BIS | Mixed (daily to quarterly) | Macro agents |
| Central Bank | Central bank APIs + scraping | Event-driven | Macro agents |
| News | NewsAPI / Reuters / Bloomberg | Real-time | All agents |
| Short Interest | S3 Partners / Ortex | Bi-weekly | Fundamental + Technical |
| Institutional Ownership | 13F filings (SEC) | Quarterly + event | Fundamental agents |
| CTA Positioning | Derived from CFTC COT + models | Weekly | Technical agent |
| Factor Returns | Computed in-house from indices | Daily | Risk agent |
| Correlation Matrix | Computed from price data | Daily (rolling 60d) | Risk agent |

### 13.3 Data Service Interface

```python
class MarketDataService(Protocol):
    """Price, volume, and derivatives data."""
    async def get_ohlcv(self, ticker: str, start: date, end: date, interval: str) -> pd.DataFrame: ...
    async def get_realtime_price(self, ticker: str) -> float: ...
    async def get_options_chain(self, ticker: str, expiry: Optional[date]) -> pd.DataFrame: ...
    async def get_short_interest(self, ticker: str) -> dict: ...
    async def get_institutional_ownership(self, ticker: str) -> dict: ...

class FundamentalDataService(Protocol):
    """Company financials, estimates, filings."""
    async def get_financials(self, ticker: str, periods: int) -> dict: ...
    async def get_estimates(self, ticker: str) -> dict: ...  # consensus + revision history
    async def get_filing_summary(self, ticker: str, filing_type: str) -> str: ...
    async def get_transcript_summary(self, ticker: str, quarter: str) -> str: ...
    async def get_peer_valuation(self, ticker: str) -> pd.DataFrame: ...

class MacroDataService(Protocol):
    """Economic indicators and macro data."""
    async def get_indicator(self, indicator: str, country: str, lookback: int) -> pd.Series: ...
    async def get_central_bank_rate(self, country: str) -> dict: ...
    async def get_fiscal_data(self, country: str) -> dict: ...
    async def get_bop_data(self, country: str) -> dict: ...
    async def get_commodity_fundamentals(self, commodity: str) -> dict: ...  # S/D, inventory, curve

class AlternativeDataService(Protocol):
    """News, sentiment, flows."""
    async def get_news(self, query: str, hours: int) -> list[dict]: ...
    async def get_sentiment(self, ticker: str) -> dict: ...
    async def get_cta_positioning(self, asset_class: str) -> dict: ...
    async def get_etf_flows(self, ticker: str, days: int) -> pd.Series: ...

class RiskDataService(Protocol):
    """Factor returns, correlations, portfolio analytics."""
    async def get_factor_returns(self, factor: str, lookback: int) -> pd.Series: ...
    async def compute_rolling_beta(self, returns: pd.Series, factor: str, window: int) -> pd.Series: ...
    async def compute_correlation_matrix(self, tickers: list[str], window: int) -> pd.DataFrame: ...
    async def compute_var(self, portfolio: dict, confidence: float) -> float: ...
```

### 13.4 Data Freshness & Caching

```yaml
caching_strategy:
  prices_eod: refresh daily at 17:00 ET
  prices_intraday: 15-minute cache TTL
  fundamentals: refresh on earnings/filing events, otherwise weekly
  estimates: refresh daily (revision-sensitive)
  macro_indicators: refresh on release schedule (varies by indicator)
  news: no cache (always fetch fresh within rate limits)
  factor_returns: compute daily after market close
  correlations: recompute daily using trailing 60-day window
  
  storage:
    hot_cache: Redis (sub-second access for active queries)
    warm_store: PostgreSQL (structured queries, joins)
    cold_store: Parquet files on local SSD (historical backtesting)
```

---

## 14. State Management & Persistence

### 14.1 Database Schema (PostgreSQL)

```sql
-- Core book state
CREATE TABLE positions (
    position_id UUID PRIMARY KEY,
    proposal_id UUID REFERENCES trade_proposals(proposal_id),
    ticker VARCHAR(10) NOT NULL,
    direction VARCHAR(5) NOT NULL,  -- 'long' or 'short'
    size_pct_nav DECIMAL(6,4),
    entry_price DECIMAL(12,4),
    current_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    take_profit DECIMAL(12,4),
    hedge_ticker VARCHAR(10),
    hedge_direction VARCHAR(5),
    hedge_size_pct_nav DECIMAL(6,4),
    hedge_entry_price DECIMAL(12,4),
    entry_date DATE NOT NULL,
    originating_agent VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',  -- active, stopped_out, target_hit, closed
    closed_date DATE,
    realized_pnl DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trade pipeline
CREATE TABLE trade_proposals (
    proposal_id UUID PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    proposal_type VARCHAR(20),  -- 'fundamental', 'macro', 'technical'
    ticker VARCHAR(10),
    direction VARCHAR(5),
    hedge_ticker VARCHAR(10),
    conviction INTEGER,
    thesis_summary TEXT,
    thesis_detail TEXT,
    target_price DECIMAL(12,4),
    stop_loss_pct DECIMAL(4,3),
    status VARCHAR(20),  -- 'proposed', 'debating', 'scored', 'risk_review', 'approved', 'rejected', 'executed', 'withdrawn'
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE TABLE debate_messages (
    message_id UUID PRIMARY KEY,
    proposal_id UUID REFERENCES trade_proposals(proposal_id),
    agent_id VARCHAR(50) NOT NULL,
    round INTEGER NOT NULL,
    stance VARCHAR(10),  -- 'support', 'challenge', 'neutral'
    argument TEXT NOT NULL,
    evidence TEXT,
    revised_conviction INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE technical_scores (
    score_id UUID PRIMARY KEY,
    proposal_id UUID REFERENCES trade_proposals(proposal_id),
    agent_id VARCHAR(50),
    technical_score INTEGER,
    trend_alignment VARCHAR(10),
    support_levels JSONB,
    resistance_levels JSONB,
    suggested_stop DECIMAL(12,4),
    suggested_target DECIMAL(12,4),
    active_signals JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE risk_decisions (
    decision_id UUID PRIMARY KEY,
    proposal_id UUID REFERENCES trade_proposals(proposal_id),
    decision VARCHAR(30),  -- 'approved', 'rejected', 'approved_with_modifications'
    rationale TEXT,
    projected_factor_betas JSONB,
    max_allowed_size DECIMAL(6,4),
    modifications JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE trade_orders (
    order_id UUID PRIMARY KEY,
    proposal_id UUID REFERENCES trade_proposals(proposal_id),
    execute BOOLEAN,
    ticker VARCHAR(10),
    direction VARCHAR(5),
    size_pct_nav DECIMAL(6,4),
    entry_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    take_profit DECIMAL(12,4),
    hedge_ticker VARCHAR(10),
    hedge_size_pct_nav DECIMAL(6,4),
    pm_rationale TEXT,
    priority VARCHAR(20),
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Portfolio analytics (computed daily)
CREATE TABLE daily_portfolio_snapshot (
    snapshot_date DATE PRIMARY KEY,
    nav DECIMAL(14,2),
    daily_return DECIMAL(8,6),
    gross_leverage DECIMAL(6,4),
    net_exposure DECIMAL(6,4),
    factor_betas JSONB,  -- {"DXY": 0.12, "SPX": -0.05, ...}
    position_count INTEGER,
    realized_pnl_ytd DECIMAL(14,2),
    unrealized_pnl DECIMAL(14,2),
    max_drawdown_from_peak DECIMAL(6,4),
    correlation_matrix_hash VARCHAR(64),  -- reference to stored correlation matrix
    created_at TIMESTAMP DEFAULT NOW()
);

-- Agent memory
CREATE TABLE agent_beliefs (
    belief_id UUID PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    belief_type VARCHAR(30),  -- 'thesis', 'watchlist', 'lesson', 'sector_view'
    content TEXT NOT NULL,
    conviction INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,  -- optional TTL for time-sensitive beliefs
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE agent_performance (
    agent_id VARCHAR(50) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    proposals_made INTEGER,
    proposals_approved INTEGER,
    trades_executed INTEGER,
    win_rate DECIMAL(4,3),
    avg_return DECIMAL(6,4),
    avg_holding_period INTEGER,  -- days
    PRIMARY KEY (agent_id, period_start)
);
```

### 14.2 Time-Series Store (TimescaleDB extension or separate)

```sql
-- High-frequency price data for technical analysis
CREATE TABLE price_history (
    ticker VARCHAR(10),
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    PRIMARY KEY (ticker, timestamp)
);

-- Factor return series
CREATE TABLE factor_returns (
    factor VARCHAR(20),
    date DATE NOT NULL,
    daily_return DECIMAL(10,8),
    PRIMARY KEY (factor, date)
);
```

---

## 15. Orchestration & Scheduling

### 15.1 Scheduler Design

```
┌───────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                 │
│  CLOCK-DRIVEN TRIGGERS                                         │
│  ├── 06:00 ET — Pre-market data refresh + overnight news scan  │
│  ├── 07:00 ET — Macro agents process overnight releases        │
│  ├── 08:00 ET — Fundamental agents scan pre-market movers      │
│  ├── 09:45 ET — Post-open technical scan (15-min settle)       │
│  ├── 12:00 ET — Midday debate resolution window                │
│  ├── 16:30 ET — Post-close data refresh + EOD analytics        │
│  ├── 17:00 ET — Daily risk report + factor beta computation    │
│  ├── 18:00 ET — PM agent daily book review                     │
│  └── Sunday 18:00 ET — Weekly deep-dive cycle (all agents)     │
│                                                                 │
│  EVENT-DRIVEN TRIGGERS                                         │
│  ├── Earnings release detected → activate relevant fund agent  │
│  ├── Central bank decision → activate relevant macro agent     │
│  ├── Stop-loss hit → alert PM + Risk                           │
│  ├── Target hit → alert PM for partial profit decision         │
│  ├── Factor beta breach approaching → alert Risk               │
│  ├── Major geopolitical event (news spike) → activate macro    │
│  └── Technical breakout/breakdown detected → alert Technical   │
│                                                                 │
│  PIPELINE MANAGEMENT                                           │
│  ├── Track all active proposals through debate stages          │
│  ├── Enforce time limits on debate rounds                      │
│  ├── Route messages between agents                             │
│  ├── Ensure sequential processing where required               │
│  └── Handle agent failures gracefully (retry, skip, alert)     │
│                                                                 │
└───────────────────────────────────────────────────────────────┘
```

### 15.2 Concurrency Model

```python
class Orchestrator:
    """Manages agent lifecycle, scheduling, and pipeline coordination."""
    
    # Agents can run in parallel for screening/research
    # But pipeline stages are sequential per-proposal
    
    async def run_daily_cycle(self):
        # Phase 1: Parallel screening (all agents scan independently)
        screening_tasks = [
            agent.run_cycle(CycleTrigger.DAILY_SCAN) 
            for agent in self.all_research_agents
        ]
        proposals = await asyncio.gather(*screening_tasks)
        
        # Phase 2: Sequential pipeline per proposal
        for proposal in self.prioritize(proposals):
            await self.run_pipeline(proposal)
    
    async def run_pipeline(self, proposal: TradeProposal):
        # Debate (may involve multiple agents, but managed sequentially)
        debate_result = await self.debate_engine.run_debate(proposal)
        if debate_result.withdrawn:
            return
        
        # Technical scoring
        tech_score = await self.technical_agent.score(proposal)
        
        # Risk gate
        risk_decision = await self.risk_agent.evaluate(proposal, tech_score)
        if risk_decision.decision == "rejected":
            return
        
        # PM decision
        order = await self.pm_agent.decide(proposal, tech_score, risk_decision)
        if order.execute:
            await self.deliver(order)
```

### 15.3 Agent Priority & Rate Limiting

```yaml
agent_priority:
  # When multiple agents want to run, priority determines order
  risk_agent: 1       # Always runs first (monitoring)
  pm_agent: 2         # Book management
  technical_agents: 3 # Real-time signals
  fundamental_agents: 4
  macro_agents: 5

rate_limits:
  llm_calls_per_minute: 60  # Shared across all agents
  llm_calls_per_agent_per_hour: 20
  data_api_calls_per_minute: 120
  proposals_per_agent_per_day: 3  # Prevent spam
  max_concurrent_debates: 5
```

---

## 16. Delivery & Interaction Layer

### 16.1 Output Channels

```
┌─────────────────────────────────────────────────────┐
│              DELIVERY LAYER                           │
├─────────────────────────────────────────────────────┤
│                                                       │
│  PRIMARY: Email Digest                               │
│  ├── Morning brief (pre-market): overnight events,   │
│  │   active proposals, book status                   │
│  ├── Trade alerts: immediate on new TradeOrder       │
│  ├── Risk alerts: factor breach / stop proximity     │
│  └── EOD summary: daily P&L, book state, activity    │
│                                                       │
│  SECONDARY: Web Dashboard (local network)            │
│  ├── Real-time book view (positions, P&L)            │
│  ├── Active pipeline (proposals in flight)           │
│  ├── Agent activity log                              │
│  ├── Debate transcripts (expandable)                 │
│  ├── Performance analytics (by agent, by sector)     │
│  └── Risk dashboard (factor betas, correlations)     │
│                                                       │
│  TERTIARY: Mobile Push (optional)                    │
│  ├── Critical alerts only (stop hit, risk breach)    │
│  └── Via Pushover / Telegram bot                     │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### 16.2 Interaction Model

The system is **advisory-only** — no auto-execution. The human operator:
- Receives recommendations via email/dashboard
- Reviews at their discretion
- Manually executes trades they agree with
- Can query any agent for deeper analysis ("why did you short XOM?")
- Can override (veto a trade, force a position review, adjust stops)
- Can inject views ("I think oil is going to $90, factor that in")

### 16.3 Secure Access from Desk

```yaml
access_model:
  # System runs on personal device (home server / always-on laptop)
  # Accessible via:
  
  option_a_vpn:
    method: WireGuard VPN from phone/tablet
    dashboard: accessible via local IP over VPN
    security: encrypted tunnel, device auth
    
  option_b_tunnel:
    method: Cloudflare Tunnel / Tailscale
    dashboard: accessible via private URL
    security: zero-trust access, SSO optional
    
  option_c_email_only:
    method: System sends to personal email
    interaction: reply-to-email commands (limited)
    security: email encryption (PGP optional)
    
  recommended: option_b_tunnel
    # Tailscale mesh network — zero config, encrypted,
    # accessible from any device with Tailscale installed,
    # no port forwarding, no public exposure
```

---

## 17. Infrastructure & Deployment

### 17.1 Hardware Requirements

```yaml
personal_server:
  # Mac Studio or equivalent always-on machine
  compute:
    cpu: Apple M-series (M2 Pro/Max or later) or AMD Ryzen 9
    ram: 64GB minimum (agent context windows + data caching)
    storage: 2TB NVMe SSD (price history, models, databases)
    gpu: not required (LLM inference is API-based)
  
  network:
    uplink: stable broadband (50+ Mbps)
    always_on: true
    ups: recommended (graceful shutdown on power loss)

alternative_cloud:
  # If personal device is impractical
  provider: Hetzner / DigitalOcean / AWS Lightsail
  spec: 8 vCPU, 32GB RAM, 500GB SSD
  cost: ~$80-150/month
  advantage: always-on without home hardware concerns
  disadvantage: data leaves your machine
```

### 17.2 Software Stack

```yaml
runtime:
  language: Python 3.12+
  async_framework: asyncio + uvloop
  task_scheduler: APScheduler (clock-driven) + custom event dispatcher
  
llm:
  primary: Anthropic Claude (Sonnet for routine, Opus for complex analysis)
  fallback: OpenAI GPT-4o (if Anthropic rate-limited)
  interface: direct SDK calls with structured output (no framework abstraction)
  
data_layer:
  database: PostgreSQL 16 + TimescaleDB extension
  cache: Redis 7 (hot data, pub/sub for message bus)
  file_storage: local filesystem (Parquet for historical data)
  
message_bus:
  implementation: Redis Streams
  # Durable, ordered, supports consumer groups
  # Each agent type is a consumer group
  # Messages persist for audit trail
  
web_dashboard:
  framework: FastAPI (backend) + HTMX or React (frontend)
  auth: single-user (API key or Tailscale identity)
  hosting: local (same machine as orchestrator)
  
email:
  provider: SendGrid or AWS SES
  templates: HTML digest format
  
monitoring:
  logging: structlog → JSON → local files + optional Loki
  metrics: Prometheus (agent latency, LLM costs, data freshness)
  alerting: Pushover / Telegram for critical alerts
```

### 17.3 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PERSONAL SERVER                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ PostgreSQL  │  │    Redis    │  │  Orchestr.  │         │
│  │ + Timescale │  │  (cache +   │  │  (Python    │         │
│  │             │  │   pub/sub)  │  │   asyncio)  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Dashboard  │  │    Data     │  │   Agent     │         │
│  │  (FastAPI)  │  │   Ingest    │  │   Workers   │         │
│  │             │  │  (scheduled)│  │   (×21)     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                               │
│  ┌─────────────────────────────────────────────────┐         │
│  │              Tailscale Mesh Network              │         │
│  │  (secure access from phone/laptop at desk)      │         │
│  └─────────────────────────────────────────────────┘         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐      ┌──────────────┐     ┌────────────┐
   │ Anthropic│      │ Data APIs    │     │ Email/Push │
   │ / OpenAI │      │ (market data)│     │  Services  │
   │   API    │      │              │     │            │
   └──────────┘      └──────────────┘     └────────────┘
```

### 17.4 Process Management

```yaml
process_supervisor: systemd (Linux) or launchd (macOS)

services:
  - name: agentic-orchestrator
    type: long-running
    restart: always
    depends_on: [postgresql, redis]
    
  - name: agentic-data-ingest
    type: long-running (with internal scheduler)
    restart: always
    depends_on: [postgresql, redis]
    
  - name: agentic-dashboard
    type: long-running
    restart: always
    depends_on: [postgresql]
    port: 8080
    
  - name: postgresql
    type: system service
    
  - name: redis
    type: system service
```

---

## 18. Security & Access

### 18.1 Threat Model

```yaml
threats:
  - description: "Unauthorized access to trade recommendations"
    mitigation: "Tailscale zero-trust networking; no public ports"
    
  - description: "API key exposure (LLM, data providers)"
    mitigation: "Environment variables; never in code; encrypted at rest"
    
  - description: "Data exfiltration of positions/strategy"
    mitigation: "All data local; no cloud storage; encrypted disk"
    
  - description: "LLM prompt injection via news/data"
    mitigation: "Input sanitization; agents have limited tool access; output validation"
    
  - description: "System compromise leading to false recommendations"
    mitigation: "All outputs are advisory; human executes manually; audit trail"
```

### 18.2 Security Controls

```yaml
network:
  - no_public_ports: true
  - tailscale_only_access: true
  - api_keys_in_env_vars: true
  - disk_encryption: FileVault (macOS) or LUKS (Linux)

application:
  - structured_output_validation: all agent outputs validated against schemas
  - input_sanitization: news/data inputs stripped of prompt-injection patterns
  - rate_limiting: per-agent and global LLM call limits
  - audit_logging: every agent action, every message, every decision

operational:
  - no_auto_execution: human reviews and manually trades
  - daily_integrity_check: verify book state consistency
  - backup: daily encrypted backup of PostgreSQL + agent memory
```

---

## 19. Monitoring & Observability

### 19.1 System Health Metrics

```yaml
infrastructure:
  - cpu_usage_per_service
  - memory_usage_per_service
  - disk_usage_and_growth_rate
  - network_latency_to_apis
  - database_connection_pool_utilization
  - redis_memory_and_hit_rate

agent_operations:
  - llm_call_latency_p50_p95_p99
  - llm_call_success_rate
  - llm_token_usage_per_agent_per_day
  - agent_cycle_duration
  - proposals_generated_per_day
  - debate_rounds_per_proposal (avg)
  - pipeline_throughput (proposals resolved per day)
  - agent_error_rate

data_freshness:
  - last_price_update_timestamp
  - last_fundamental_refresh_per_ticker
  - last_macro_indicator_update_per_series
  - stale_data_alerts (>24hr for daily data)

trading_performance:
  - daily_pnl (realized + unrealized)
  - drawdown_from_peak
  - factor_betas_current
  - gross_and_net_leverage
  - win_rate_rolling_30d
  - average_holding_period
  - stop_loss_hit_rate
  - target_hit_rate
```

### 19.2 Alerting Rules

```yaml
critical_alerts:  # Immediate push notification
  - factor_beta_breach: "Any factor beta exceeds ±0.55 (approaching limit)"
  - drawdown_threshold: "Drawdown from peak exceeds 2%"
  - stop_loss_hit: "Position hit stop-loss level"
  - system_down: "Orchestrator or database unresponsive >5 min"
  - data_stale: "No price update in >2 hours during market hours"

warning_alerts:  # Email / dashboard highlight
  - high_correlation: "Book average pairwise correlation >0.35"
  - concentrated_position: "Single position approaching 5% NAV"
  - agent_underperformance: "Agent win rate <30% over trailing 20 trades"
  - llm_cost_spike: "Daily LLM spend >$50 (unusual activity)"
  - proposal_rejection_rate: ">80% of proposals rejected by risk in a week"

informational:  # Dashboard only
  - new_trade_order_generated
  - debate_concluded
  - weekly_performance_summary
  - agent_belief_update
```

---

## 20. Performance & Scaling

### 20.1 Bottleneck Analysis

```yaml
primary_bottleneck: LLM API latency and rate limits
  - Each agent cycle: 1-3 LLM calls (context assembly, reasoning, output)
  - Debate round: 2-4 LLM calls per participating agent
  - Full pipeline (proposal → order): 10-20 LLM calls total
  - At 2-3 seconds per call: 20-60 seconds per pipeline run
  
  mitigation:
    - Parallel screening (all 17 research agents scan simultaneously)
    - Sequential pipeline only where required (debate → score → risk → PM)
    - Pre-compute and cache context windows (reduce token usage)
    - Use smaller/faster models for routine tasks (screening, data parsing)
    - Reserve large models for complex reasoning (debate, PM decisions)

secondary_bottleneck: Data API rate limits
  mitigation:
    - Aggressive caching with smart invalidation
    - Batch requests where APIs support it
    - Stagger agent cycles to spread load
    - Pre-fetch predictable data needs (scheduled refreshes)
```

### 20.2 Scaling Strategy (if needed)

```yaml
vertical_scaling:  # First approach — same machine, more capacity
  - More RAM for larger context windows
  - Faster SSD for database performance
  - Better CPU for data processing

horizontal_scaling:  # If single machine becomes insufficient
  - Split agents across multiple processes (already async)
  - Database on dedicated machine
  - Redis cluster for message bus
  - Multiple LLM API keys for higher rate limits
  
  # Unlikely to be needed for 21 agents on daily cycle
  # Only relevant if moving to intraday/real-time operation
```

---

## 21. Failure Modes & Recovery

### 21.1 Failure Scenarios

```yaml
llm_api_outage:
  impact: Agents cannot reason or generate proposals
  detection: API call failure rate > 50% in 5-minute window
  response:
    - Failover to secondary provider (OpenAI ↔ Anthropic)
    - If both down: pause new proposals, maintain existing positions
    - Risk monitoring continues (rule-based, no LLM needed for stop checks)
  recovery: Resume normal cycle when API restored

data_feed_failure:
  impact: Agents working with stale data
  detection: Data freshness alerts trigger
  response:
    - Flag all proposals generated during outage as "stale_data"
    - Risk agent applies wider margins (reduce max position size 50%)
    - Technical agent disables intraday signals
  recovery: Full data refresh + re-run screening cycle

database_corruption:
  impact: Book state unreliable
  detection: Integrity check failure
  response:
    - Halt all new proposals
    - Alert operator immediately
    - Restore from most recent backup
    - Reconcile with known positions (manual verification)
  recovery: Operator confirms book state before resuming

agent_hallucination:
  impact: Nonsensical proposals or decisions
  detection: Output validation failures; proposals for non-existent tickers; impossible prices
  response:
    - Reject invalid output; retry with fresh context
    - If 3 consecutive failures: disable agent, alert operator
    - Log for prompt engineering review
  recovery: Prompt revision; context window audit

orchestrator_crash:
  impact: No agent cycles running
  detection: Heartbeat failure (no log entry in 10 minutes)
  response:
    - systemd/launchd auto-restart
    - On restart: check for in-flight proposals, resume or roll back
    - Alert operator if restart fails twice
  recovery: Automatic in most cases; manual intervention for data consistency
```

### 21.2 Data Integrity Guarantees

```yaml
consistency:
  - All state changes are transactional (PostgreSQL ACID)
  - Message bus uses Redis Streams with acknowledgment (at-least-once delivery)
  - Agent outputs validated before persisting
  - Book state reconciliation runs daily (positions match trade log)
  
durability:
  - PostgreSQL WAL + daily full backup
  - Redis AOF persistence (append-only file)
  - Backup to encrypted external drive (weekly)
  - Agent memory exportable as JSON (for migration/recovery)
```

---

## 22. Cost Model

### 22.1 Ongoing Monthly Costs (Estimated)

```yaml
llm_api:
  # 21 agents × ~3 cycles/day × ~3 calls/cycle × 30 days = ~5,670 calls/month
  # Plus debates: ~10 proposals/day × 15 calls/debate × 30 = ~4,500 calls/month
  # Plus monitoring/misc: ~2,000 calls/month
  # Total: ~12,000 calls/month
  
  # Average cost per call (mixed Sonnet + Opus):
  # Sonnet: ~$0.015/call (3K input + 1K output tokens avg)
  # Opus/large: ~$0.08/call (5K input + 2K output tokens avg)
  # Mix (80% Sonnet, 20% Opus): ~$0.028/call avg
  
  estimated_monthly: $350 - $500
  with_buffer: $600  # spikes during high-activity periods

data_apis:
  polygon_io: $200/month (full market data)
  # OR
  alpaca: $0 (free tier for delayed) / $99 (real-time)
  fred_api: $0 (free)
  newsapi: $50/month (business tier)
  sec_edgar: $0 (free, rate-limited)
  
  estimated_monthly: $100 - $300

infrastructure:
  personal_hardware: $0 ongoing (one-time purchase ~$3,000-5,000)
  # OR cloud:
  cloud_server: $80 - $150/month
  
  electricity: ~$20/month (always-on Mac Studio)
  internet: existing connection
  tailscale: $0 (free for personal use)
  
  estimated_monthly: $20 - $150

email_delivery:
  sendgrid: $0 (free tier: 100 emails/day is sufficient)

total_estimated_monthly: $470 - $1,050
recommended_budget: $750/month
```

### 22.2 One-Time Setup Costs

```yaml
hardware:
  mac_studio_m2_max: $3,000 - $4,000
  ups_battery_backup: $150
  external_backup_drive: $100
  
development:
  time_investment: 200-400 hours (if self-built)
  # OR contracted development: $50,000 - $100,000
  
data_history:
  historical_price_data: $0 (available from free sources for backtest)
  historical_fundamentals: $0 - $500 (SimFin premium or similar)
```

---

## 23. Development Phases

### Phase 1: Foundation (Weeks 1-4)
```
- Data service implementation (market data + fundamentals + macro)
- Database schema + state management
- Message bus (Redis Streams)
- Agent base class with LLM integration
- Basic orchestrator (manual trigger)
- Output: Data flows, agents can be invoked, messages persist
```

### Phase 2: Agent Development (Weeks 5-10)
```
- System prompts for all 21 agents (sector/region specific)
- Structured output schemas + validation
- Agent memory system (beliefs, episodic, semantic)
- 1 fundamental agent (Energy) fully operational
- 1 macro agent (Commodities) fully operational
- Technical agent fully operational
- Risk agent fully operational
- PM agent fully operational
- Output: Full pipeline works for Energy/Commodities subset
```

### Phase 3: Debate & Pipeline (Weeks 11-14)
```
- Debate engine (multi-round, conviction tracking, evidence requirement)
- Full pipeline orchestration (proposal → debate → score → risk → PM)
- Time-boxing and priority management
- Audit trail and logging
- Output: End-to-end pipeline producing trade orders
```

### Phase 4: Scale to Full Universe (Weeks 15-20)
```
- Remaining 10 fundamental agents (prompts + sector KPIs)
- Remaining 5 macro agents (prompts + regional frameworks)
- Second technical agent (commodity-specific)
- Cross-agent debate routing (sector agent challenges macro agent, etc.)
- Performance tracking per agent
- Output: All 21 agents operational, full universe coverage
```

### Phase 5: Delivery & Interaction (Weeks 21-24)
```
- Email digest system (morning brief, trade alerts, EOD summary)
- Web dashboard (positions, pipeline, debates, performance)
- Tailscale networking setup
- Mobile push notifications (critical alerts)
- Query interface (ask agents questions on-demand)
- Output: Full interaction layer, accessible from desk
```

### Phase 6: Hardening & Optimization (Weeks 25-30)
```
- Failure recovery testing
- Data integrity validation
- LLM cost optimization (prompt compression, model routing)
- Agent prompt tuning based on early results
- Backtesting framework (replay historical data through pipeline)
- Performance attribution (which agents generate alpha)
- Output: Production-ready system
```

---

## Appendix A: Agent System Prompt Structure

Each agent's system prompt follows this template:

```
IDENTITY: You are [role] at [firm type]. Your specialty is [domain].

MANDATE: Your job is to [primary objective]. You [can/cannot] [specific authorities].

ANALYTICAL FRAMEWORK: When analyzing [domain], you evaluate:
1. [Framework element 1]
2. [Framework element 2]
...

SECTOR/REGION SPECIFIC: In your domain, the key drivers are:
- [Driver 1]: [why it matters]
- [Driver 2]: [why it matters]
...

RISK AWARENESS: You always consider:
- [Risk constraint 1]
- [Risk constraint 2]

OUTPUT FORMAT: You must produce [structured output type] with the following fields:
[schema description]

DEBATE PROTOCOL: When debating:
- Support claims with specific data points
- Challenge weak logic, not just disagree
- Revise conviction honestly when evidence warrants
- Never argue from authority; argue from data

CONSTRAINTS:
- [Hard constraint 1]
- [Hard constraint 2]
- [Hedge requirement]
- [Position limits]
```

---

## Appendix B: Sample Daily Cycle Timeline

```
06:00 ET │ Data ingest: overnight prices, news, macro releases
06:30 ET │ Macro agents process: LatAm, CEEMEA, Asia overnight events
07:00 ET │ Fundamental agents: pre-market scan (earnings, news, upgrades/downgrades)
07:30 ET │ Technical agents: gap analysis, overnight levels
08:00 ET │ Proposals published (if any high-conviction ideas emerged)
08:00-12:00 │ Debate window (asynchronous rounds)
09:45 ET │ Post-open technical update (confirm/deny overnight setups)
12:00 ET │ Debate resolution deadline
12:30 ET │ Technical scoring of surviving proposals
13:00 ET │ Risk evaluation
13:30 ET │ PM decision + trade order generation
14:00 ET │ Trade orders delivered to operator
16:30 ET │ EOD data refresh
17:00 ET │ Risk report: factor betas, correlation check, drawdown status
17:30 ET │ Position monitoring: stop proximity, target proximity
18:00 ET │ PM daily review: any adjustments needed?
18:30 ET │ EOD digest email sent to operator
```

---

## Appendix C: Factor Beta Calculation Methodology

```python
def compute_factor_betas(book_returns: pd.Series, factor_returns: pd.DataFrame, window: int = 252) -> dict:
    """
    Compute rolling 12-month (252 trading day) factor betas for the book.
    
    Method: Univariate OLS regression of book daily returns against each factor's daily returns.
    
    For each factor f:
        beta_f = Cov(R_book, R_f) / Var(R_f)
        
    Using the trailing 252 trading days of data.
    
    Returns: {"DXY": 0.15, "SPX": -0.08, ...}
    """
    betas = {}
    book_window = book_returns.iloc[-window:]
    
    for factor_name in TRACKED_FACTORS:
        factor_window = factor_returns[factor_name].iloc[-window:]
        
        # OLS: R_book = alpha + beta * R_factor + epsilon
        cov = book_window.cov(factor_window)
        var = factor_window.var()
        betas[factor_name] = cov / var if var > 0 else 0.0
    
    return betas

# Hard constraint enforcement:
def check_factor_limits(betas: dict) -> list[str]:
    violations = []
    for factor, beta in betas.items():
        if abs(beta) > 0.6:
            violations.append(f"BREACH: {factor} beta = {beta:.3f} (limit ±0.6)")
        elif abs(beta) > 0.5:
            violations.append(f"WARNING: {factor} beta = {beta:.3f} (approaching limit)")
    return violations
```

---

*End of Production Design Document*
