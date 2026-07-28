---
name: trading-news
description: Fetch news headlines, earnings calendar, detect news spikes, and check upcoming macro events for market awareness.
---

# Trading News

Use the `exec` tool to call the data platform CLI for news and events. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Get recent headlines for a ticker
```bash
python -m data_platform.cli news headlines --ticker XOM --max 10
```
Returns: list of headlines with title, source, date, relevance.

### Check earnings calendar
```bash
python -m data_platform.cli news earnings --tickers XOM CVX COP EOG SLB MPC PSX VLO OXY DVN
```
Returns: upcoming earnings dates for all tickers, sorted by soonest.

### Filter to upcoming earnings (within N days)
```bash
python -m data_platform.cli news upcoming-earnings --tickers XOM CVX COP --days 14
```
Returns: only events within the next 14 days.

### Detect news spike (unusual headline volume)
```bash
python -m data_platform.cli news spike --ticker XOM
```
Returns: whether headline volume is abnormal, spike ratio, sample headlines.

### Check upcoming macro events
```bash
python -m data_platform.cli news macro-events --days 7
```
Returns: scheduled economic releases (NFP, CPI, FOMC, ISM) in the next 7 days.

## When to use

- Before proposing any trade: check headlines for the ticker (anything market-moving?)
- Check earnings calendar: are any of your names reporting soon? (catalyst or risk)
- Check macro events: is there an FOMC/CPI/NFP that could move the sector?
- News spike detection: high volume of headlines = something is happening, investigate further
