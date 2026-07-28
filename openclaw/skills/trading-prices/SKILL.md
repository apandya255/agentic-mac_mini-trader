---
name: trading-prices
description: Fetch price data, compute returns, pair ratios, and relative strength for equities and ETFs in the trading universe.
---

# Trading Prices

Use the `exec` tool to call the data platform CLI for price-related queries. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Get trailing returns for a ticker
```bash
python -m data_platform.cli prices returns --ticker XOM
```
Returns: `{"ticker": "XOM", "returns": {"1D": 0.012, "1W": -0.005, "1M": 0.034, "3M": -0.02, "6M": 0.08, "1Y": 0.15}}`

### Get pair ratio (book representation format)
```bash
python -m data_platform.cli prices pair-ratio --ticker XLE --hedge RSP
```
Returns: current ratio, z-score (how extreme vs. history), percentile rank, 52-week range.

### Get price history (last N days)
```bash
python -m data_platform.cli prices history --ticker XOM --lookback 20
```
Returns: array of OHLCV data points.

### Get relative strength vs. benchmark
```bash
python -m data_platform.cli prices relative-strength --ticker XOM --benchmark XLE --lookback 63
```
Returns: outperformance/underperformance vs. benchmark over the period.

### Update price database (fetch latest)
```bash
python -m data_platform.cli prices update --tickers XOM CVX COP EOG SLB MPC PSX VLO OXY DVN XLE RSPG RSP USO XOP GLD
```
Run this before analysis to ensure data is current.

## When to use

- Before any trade analysis, check returns across timeframes
- Use pair-ratio to understand the spread vs. hedge
- Use relative-strength to identify outperformers/laggards within the sector
- Always cite specific return numbers in proposals and debates
