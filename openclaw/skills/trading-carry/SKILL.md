---
name: trading-carry
description: Compute SOFR rate, daily carry on cash, and position-level carry costs for portfolio NAV accounting.
---

# Trading Carry

Use the `exec` tool to call the data platform CLI for carry computations. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Get current SOFR rate
```bash
python -m data_platform.cli carry rate
```
Returns: current SOFR rate as decimal and percentage.

### Compute daily cash carry
```bash
python -m data_platform.cli carry cash --cash-pct 0.40
```
Returns: daily carry in USD earned on the cash allocation (cash × SOFR / 360).

### Compute position carry cost
```bash
python -m data_platform.cli carry position-cost --direction long --notional 400000 --ticker XOM
```
Returns: daily opportunity cost (longs) or borrow cost (shorts) in USD and bps.

## Context

- Cash earns SOFR daily (actual/360 day count)
- Long positions have an opportunity cost (capital deployed instead of earning SOFR)
- Short positions have a borrow cost (~50bps annualized for liquid names)
- PM should consider net carry when deciding between similar opportunities

## When to use

- PM agent: check carry impact when deciding between trades
- PM agent: understand the cost of holding positions vs. cash
- Useful for comparing a marginal trade vs. staying in cash
