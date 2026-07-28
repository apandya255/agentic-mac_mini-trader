---
name: trading-sizing
description: Compute position sizes based on conviction level, high-conviction tier rules, and circuit breaker adjustments.
---

# Trading Sizing

Use the `exec` tool to call the data platform CLI for position sizing. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Compute size for a given conviction
```bash
python -m data_platform.cli sizing compute --conviction 8
```
Returns: size_pct_nav, size_dollars, tier, rationale.

### Compute high-conviction tier size
```bash
python -m data_platform.cli sizing compute --conviction 9 --high-conviction
```
Returns: 8% size if HC slots available, otherwise falls back to standard.

### With circuit breaker adjustment
```bash
python -m data_platform.cli sizing compute --conviction 8 --cb-mult 0.8
```
Returns: size reduced by circuit breaker multiplier.

### Show full sizing table
```bash
python -m data_platform.cli sizing table
```
Returns: all conviction levels with corresponding sizes in % and dollars.

## Sizing Rules

| Conviction | Size |
|-----------|------|
| 1-4 | 2% NAV |
| 5-6 | 3% NAV |
| 7-8 | 4% NAV |
| 9-10 | 5% NAV |
| HC (8+) | 8% NAV (max 2 slots) |

Adjustments:
- Circuit breaker warning: ×0.8
- Circuit breaker halt: ×0.0 (no new positions)

## When to use

- PM agent: compute final size for every trade order
- Risk agent: verify proposed size is within limits
- Always apply circuit breaker multiplier from the current book state
