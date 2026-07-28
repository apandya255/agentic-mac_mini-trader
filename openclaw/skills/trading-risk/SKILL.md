---
name: trading-risk
description: Compute risk metrics — circuit breaker status, trailing stop levels, position correlations, and crowding detection.
---

# Trading Risk

Use the `exec` tool to call the data platform CLI for risk computations. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Check circuit breaker status
```bash
python -m data_platform.cli risk circuit-breaker --nav 9850000
```
Returns: drawdown %, status (normal/warning/breaker), sizing multiplier, max leverage, recovery eligibility.

### Compute trailing stop level for a position
```bash
python -m data_platform.cli risk trailing-stop --ticker XOM --direction long --entry-price 105 --peak-price 112 --current-price 109 --trail-pct 0.025
```
Returns: stop level, distance to stop, P&L %, gains locked, is_stopped flag, is_target_review flag.

### Check correlation between positions
```bash
python -m data_platform.cli risk correlation --tickers XOM CVX COP
```
Returns: pairwise correlation matrix (rolling 60-day).

### Check for crowding
```bash
python -m data_platform.cli risk crowding --tickers XOM CVX COP EOG
```
Returns: crowded clusters (pairs > 0.6 correlation), average pairwise correlation, alerts.

## Key Limits to Enforce

| Metric | Limit |
|--------|-------|
| Factor beta | ±0.6 per factor |
| Single position | 5% NAV (8% HC) |
| Sector gross | 25% NAV |
| Pairwise correlation | < 0.7 |
| Book avg correlation | < 0.4 (alert) |
| Circuit breaker warning | 4% drawdown |
| Circuit breaker halt | 6% drawdown |

## When to use

- Risk agent: run circuit-breaker and correlation checks on EVERY proposal evaluation
- PM agent: check circuit breaker before sizing (get the sizing multiplier)
- All agents: trailing-stop to understand current position risk
