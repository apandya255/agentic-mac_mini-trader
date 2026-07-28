---
name: trading-universe
description: Look up hedge pairs, sector classifications, and universe listings for the trading system.
---

# Trading Universe

Use the `exec` tool to call the data platform CLI for universe lookups. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Resolve the hedge for a ticker
```bash
python -m data_platform.cli universe hedge --ticker XOM --direction long
```
Returns: primary ticker, direction, hedge ticker, hedge direction.

Hedge rules:
- Single name → equal-weight sector ETF (XOM long → RSPG short)
- Sector ETF → RSP (XLE long → RSP short)
- Country ETF (DM) → EFA (EM) → EEM
- Commodity → ACWI

### Get sector classification and constituents
```bash
python -m data_platform.cli universe sector --ticker XOM
```
Returns: sector name, sector ETF, EW hedge ETF, all sector constituents.

### List the full universe
```bash
python -m data_platform.cli universe list
```
Returns: all ticker categories with counts (S&P 500, sector ETFs, country ETFs, commodities, hedges).

## When to use

- ALWAYS use `hedge` before constructing a trade to get the correct hedge instrument
- Use `sector` to identify peers for comparison
- Don't hardcode hedge mappings — let the tool resolve them
