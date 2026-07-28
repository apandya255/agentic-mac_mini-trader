---
name: trading-valuations
description: Fetch fundamental valuation metrics (P/E, EV/EBITDA, margins, analyst targets) and run peer comparisons for equity analysis.
---

# Trading Valuations

Use the `exec` tool to call the data platform CLI for valuation data. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Get valuation snapshot for a single name
```bash
python -m data_platform.cli valuations snapshot --ticker XOM
```

Returns:
- Price and market cap
- Multiples: P/E (trailing + forward), EV/EBITDA, P/B, P/Sales, dividend yield
- Growth: revenue growth YoY, earnings growth YoY
- Margins: gross, operating, net, FCF yield
- Balance sheet: debt/equity, current ratio, ROE
- Analyst: target price (mean/high/low), recommendation, # analysts
- Next earnings date

### Run peer comparison
```bash
python -m data_platform.cli valuations peers --ticker XOM --peers CVX COP EOG SLB
```

Returns:
- Percentile rankings vs. peers (P/E, EV/EBITDA, dividend yield)
- Ratio vs. peer median (0.8 = 20% discount to peers)
- Operating margin vs. peer median
- Relative value verdict: "cheap" / "fair" / "expensive"

## When to use

- Fundamental agent: use on every name you analyze
- Always compare vs. peers — absolute valuation means nothing without context
- Check both trailing AND forward multiples
- Look at FCF yield for capital-return stories
- Cite specific multiples in your thesis ("XOM at 10.5x forward EV/EBITDA vs. peer median 12.2x")
