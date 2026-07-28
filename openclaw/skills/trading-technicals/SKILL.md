---
name: trading-technicals
description: Run full technical analysis scans on tickers — moving averages, RSI, MACD, KST, ADX, Bollinger Bands, Fibonacci levels, volume signals, and composite score.
---

# Trading Technicals

Use the `exec` tool to call the data platform CLI for technical analysis. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Full technical scan (PRIMARY command)
```bash
python -m data_platform.cli technicals scan --ticker XOM
```

Returns a complete technical snapshot:
- **overall_score** (1-10): composite technical assessment
- **bias**: "bullish" / "bearish" / "neutral"
- **moving_averages**: SMA/EMA 20/50/100/200, crossover status, price position vs. MAs
- **momentum**: RSI(14), MACD (line/signal/histogram/crossover), KST, ADX trend strength
- **volatility**: Bollinger Bands (upper/middle/lower/width/squeeze), ATR(14)
- **volume**: OBV trend, volume vs. 20-day avg, unusual volume flag
- **fibonacci**: swing high/low, retracement levels (23.6%, 38.2%, 50%, 61.8%), extension levels

## Interpreting the Score

| Score | Meaning |
|-------|---------|
| 1-3 | Poor technical setup — technicals against the proposed direction |
| 4-5 | Neutral — no technical edge either way |
| 6-7 | Supportive — technicals confirm the direction |
| 8-10 | Strong — technicals strongly confirm with clear levels and momentum |

## When to use

- Technical agent: use on EVERY proposal you score
- Other agents: use for a quick technical check before proposing a trade
- Always run the full scan — don't cherry-pick individual indicators
- Report the composite score AND the key individual signals that drive it
