# Data Platform — Pipeline Integration Guide

How to wire these 12 modules into the orchestrator/agent pipeline.

---

## Module Dependency Graph

```
                    ┌────────────────┐
                    │   universe.py  │  ← everything references this
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────────┐
              │             │                 │
       ┌──────▼──────┐  ┌──▼────────┐  ┌────▼──────┐
       │  prices.py  │  │ carry.py  │  │ macro_data │
       └──────┬──────┘  └───────────┘  └───────────┘
              │
    ┌─────────┼──────────────────────────┐
    │         │         │                │
┌───▼───┐ ┌──▼───┐ ┌───▼────┐ ┌────────▼────────┐
│ tech- │ │ val- │ │ factor │ │    book.py      │
│ nicals│ │ uat- │ │ _betas │ │ (uses trailing_ │
│       │ │ ions │ │        │ │  stop, sizing)  │
└───────┘ └──────┘ └───┬────┘ └────────┬────────┘
                        │               │
                   ┌────▼────┐   ┌──────▼──────┐
                   │ circuit │   │    news.py  │
                   │ breaker │   └─────────────┘
                   └─────────┘
```

---

## Daily Pipeline (What Calls What, In Order)

### 1. Data Refresh (16:30 ET or on schedule)

```python
from data_platform import PriceService, Universe, MacroDataService, CarryCalculator

# Price data
svc = PriceService()
u = Universe()
u.load()
svc.update(u.all_tickers(), progress=True)

# Macro data (requires FRED API key)
mds = MacroDataService(fred_api_key="YOUR_KEY")
mds.refresh()  # fetches all 45+ indicators

# SOFR rate
carry = CarryCalculator(fred_api_key="YOUR_KEY")
carry.refresh_sofr()
```

### 2. Mark Book to Market (17:00 ET)

```python
from data_platform import Book

book = Book(nav=650_000_000)
# ... (positions loaded from persistent state) ...
book.mark_to_market(svc)
```

After mark-to-market, every position has:
- Updated `current_price` and `hedge_current_price`
- Recomputed `pair_ratio` (the "XLE/RSP @ 0.52" representation)
- Updated trailing stop (ratcheted if new high)
- `status` set to "stopped_out" or "target_review" if triggered

### 3. Risk Checks (17:00 ET)

```python
from data_platform import FactorBetaCalculator, BookMonitor
from data_platform.trailing_stop import monitor_positions

# Factor betas
beta_calc = FactorBetaCalculator(price_service=svc)
book_returns = book.compute_daily_returns(svc, lookback_days=252)
betas = beta_calc.compute_betas(book_returns)
violations = beta_calc.check_limits(betas)

# Correlation / crowding
active_tickers = [p.ticker for p in book.active_positions]
crowding = beta_calc.crowding_check(active_tickers, window=60)

# Circuit breaker
monitor = BookMonitor(initial_nav=650_000_000)
monitor.update_nav(book.current_nav)
alert = monitor.alert_message()  # None if normal

# Trailing stop alerts
stops = [p.trailing_stop for p in book.active_positions if p.trailing_stop]
stop_alerts = monitor_positions(stops)
```

### 4. Agent Research Cycles (Scheduled or Event-Driven)

#### Fundamental Agent needs:

```python
from data_platform import PriceService, ValuationService, TechnicalAnalysis, NewsScanner
from data_platform.universe import Universe

vs = ValuationService()
ta = TechnicalAnalysis(price_service=svc)
news = NewsScanner()

# For a single name analysis
snap = vs.get_snapshot("XOM")               # valuation metrics
peers = vs.peer_comparison("XOM", ["CVX", "COP", "EOG", "SLB"])
tech = ta.full_scan("XOM")                  # technical picture
returns = svc.compute_returns("XOM")        # trailing returns
rel_str = svc.relative_strength("XOM", "XLE", 63)  # vs sector
headlines = news.get_headlines("XOM")       # recent news
```

#### Macro Agent needs:

```python
from data_platform import MacroDataService

mds = MacroDataService(fred_api_key="YOUR_KEY")

# Regional macro picture
curve = mds.yield_curve()
inflation = mds.inflation_snapshot()
labor = mds.labor_snapshot()
credit = mds.credit_snapshot()

# Specific indicators
gdp = mds.get_series("US_GDP_GROWTH", lookback_days=730)
pmi = mds.get_indicator("US_ISM_MFG")
hy_spread = mds.get_series("US_HY_SPREAD", lookback_days=365)
```

#### Technical Agent needs:

```python
from data_platform import TechnicalAnalysis

ta = TechnicalAnalysis(price_service=svc)

# Score a proposed trade
snapshot = ta.full_scan("XOM")
print(snapshot.overall_score)      # 1-10
print(snapshot.bias)               # "bullish" / "bearish" / "neutral"
print(snapshot.momentum.rsi_14)    # RSI value
print(snapshot.fibonacci)          # support/resistance levels
```

### 5. Pre-Trade Risk Check (Before Adding a Position)

```python
from data_platform import FactorBetaCalculator, PositionSizer, BookMonitor

# Check if new position would breach factor limits
position_returns = svc.compute_daily_returns("XOM", 252)
projected = beta_calc.project_beta_impact(
    current_betas=betas,
    new_position_returns=position_returns,
    new_position_weight=0.04,  # 4% NAV
)
projected_violations = beta_calc.check_limits(projected)

# Size the position
sizer = PositionSizer(nav=650_000_000)
size = sizer.compute_size(
    conviction=8,
    high_conviction=False,
    circuit_breaker_mult=monitor.sizing_multiplier(),
)

# If approved, add to book
if not projected_violations:
    book.add_position(
        ticker="XOM",
        direction="long",
        entry_price=105.0,
        size_pct=size.size_pct_nav,
        conviction=8,
        hedge_entry_price=88.50,  # RSPG price
    )
```

### 6. Carry Computation (EOD)

```python
from data_platform import CarryCalculator

carry = CarryCalculator(fred_api_key="YOUR_KEY", nav=650_000_000)

# Book-level carry
positions_for_carry = [
    {"ticker": p.ticker, "direction": p.direction, 
     "notional": 650_000_000 * p.size_pct_nav}
    for p in book.active_positions
]
carry_summary = carry.book_carry_summary(positions_for_carry, cash_pct=book.cash_pct)
```

### 7. Output: Blotter + Summary (EOD Report)

```python
# One-line-per-position format
for line in book.blotter():
    print(line)
# Output:
# XOM/RSPG @ 1.1864  +1.8%  [8/10 S]  long 4.0%  trail@103.25
# XLE/RSP @ 0.5452  +2.1%  [7/10 S]  long 3.0%  trail@87.50  [PM REVIEW]

# Summary dict (for email/dashboard)
summary = book.summary()
# {'nav': 653250000, 'position_count': 5, 'gross_exposure_pct': 0.28, ...}
```

---

## Event-Driven Triggers

| Event | What To Call |
|-------|-------------|
| Earnings release detected | `news.earnings_calendar(tickers)` → flag relevant fundamental agent |
| Price hits trailing stop | `monitor_positions(stops)` → alert PM + Risk |
| Position hits +5% | `TrailingStop.is_target_review` → PM review (take is default) |
| Factor beta approaching limit | `beta_calc.check_limits(betas)` → alert Risk agent |
| Book drawdown hits 4% | `BookMonitor.status == "warning"` → reduce sizing 20% |
| Unusual news volume | `news.detect_news_spike(ticker)` → activate relevant agent |
| New trade proposed | `beta_calc.project_beta_impact(...)` → pre-trade risk check |

---

## How the Orchestrator Wires This

The orchestrator (on the Mini) owns the scheduling and agent invocation.
These modules are the **functions it calls**. Typical orchestrator structure:

```python
import asyncio
from data_platform import *

async def daily_cycle():
    # 1. Refresh data
    svc.update(universe.all_tickers())
    mds.refresh()
    carry_calc.refresh_sofr()
    
    # 2. Mark to market
    book.mark_to_market(svc)
    
    # 3. Risk checks
    betas = beta_calc.compute_betas(book.compute_daily_returns(svc))
    monitor.update_nav(book.current_nav)
    alerts = monitor_positions(active_stops)
    
    # 4. Handle alerts (stopped positions, breaches)
    for alert in alerts:
        if alert.alert_type == "stopped_out":
            book.close_position(alert.ticker, reason="trailing_stop")
    
    # 5. Run agent research cycles (parallel)
    proposals = await asyncio.gather(*[
        agent.run_cycle() for agent in research_agents
    ])
    
    # 6. Pipeline each proposal (sequential)
    for proposal in proposals:
        # debate → technical score → risk gate → PM decision
        ...
    
    # 7. Generate reports
    send_eod_report(book.summary(), book.blotter(), betas, carry_summary)
```

---

## Persistent State

These modules are **stateless per invocation** (except in-memory caches).
For persistence across runs, the orchestrator should:

1. **SQLite databases** (auto-created):
   - `data/prices.db` — price history (survives restarts)
   - `data/carry.db` — SOFR rates
   - `data/macro.db` — macro indicator cache

2. **Book state** — serialize `book.positions` + `book.trade_journal` to JSON/SQLite between runs. The `Book` class doesn't persist itself — the orchestrator owns that.

3. **Trailing stops** — embedded in each `Position` object. If you serialize positions, stops come with them.

---

## API Keys Required

| Service | Key Source | What It Unlocks |
|---------|-----------|-----------------|
| yfinance | None needed | Prices, fundamentals, news, earnings calendar |
| FRED | https://fred.stlouisfed.org/docs/api/api_key.html (free) | SOFR rate, 45+ macro indicators |
| NewsAPI | https://newsapi.org (free tier: 100 req/day) | Broader news search (optional) |

---

## Quick Start (5 minutes)

```python
import sys
sys.path.insert(0, "src")

from data_platform import PriceService, Universe, Book, TechnicalAnalysis, PositionSizer

# 1. Load universe
u = Universe()
u.load()

# 2. Fetch prices for a few tickers
svc = PriceService()
svc.update(["XOM", "RSPG", "XLE", "RSP", "SPY"], lookback_days=400)

# 3. Run technicals
ta = TechnicalAnalysis(price_service=svc)
snapshot = ta.full_scan("XOM")
print(f"XOM technical score: {snapshot.overall_score}/10 ({snapshot.bias})")

# 4. Size a position
sizer = PositionSizer(nav=650_000_000)
size = sizer.compute_size(conviction=8)
print(f"Size: {size.size_pct_nav*100}% NAV = ${size.size_dollars:,.0f}")

# 5. Create a book and add a position
book = Book(nav=650_000_000)
pos = book.add_position("XOM", "long", entry_price=105.0, size_pct=0.04, 
                         conviction=8, hedge_entry_price=88.50)
print(f"Position: {pos.pair_display}")
print(f"Trailing stop at: ${pos.trailing_stop.stop_level:.2f}")

# 6. Print blotter
for line in book.blotter():
    print(line)
```
