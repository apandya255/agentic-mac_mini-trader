---
name: trading-macro
description: Fetch macroeconomic indicators from FRED — oil prices, DXY, yield curve, inflation, credit spreads, and upcoming macro events.
---

# Trading Macro

Use the `exec` tool to call the data platform CLI for macro data. All commands return JSON.

## Prerequisites

Working directory must be set so Python can find the modules:
```
cd {baseDir}/../../../src
```

## Commands

### Get a specific macro indicator
```bash
python -m data_platform.cli macro indicator --name WTI_CRUDE
python -m data_platform.cli macro indicator --name DXY_BROAD
python -m data_platform.cli macro indicator --name US_HY_SPREAD
python -m data_platform.cli macro indicator --name VIX
```

Returns: latest value, prior value, change, date.

### Get yield curve snapshot
```bash
python -m data_platform.cli macro yield-curve
```
Returns: 2Y, 5Y, 10Y, 30Y yields + 2s10s spread + curve shape (normal/flat/inverted).

### Get inflation data
```bash
python -m data_platform.cli macro inflation
```
Returns: CPI, core CPI, PCE, breakevens.

### Get credit conditions
```bash
python -m data_platform.cli macro credit
```
Returns: HY spread, IG spread, Chicago FCI, VIX.

### List all available indicators
```bash
python -m data_platform.cli macro list
```
Returns: all 45+ indicator names you can query.

### Check data freshness
```bash
python -m data_platform.cli macro freshness
```
Returns: last update date for each cached indicator.

## Available Indicators (Key Ones)

| Name | Description |
|------|-------------|
| WTI_CRUDE | WTI crude oil spot price |
| DXY_BROAD | Trade-weighted US dollar |
| GOLD_PRICE | Gold fixing price |
| US_10Y | 10-year Treasury yield |
| US_2S10S | 2s10s spread |
| US_HY_SPREAD | HY OAS |
| VIX | CBOE VIX |
| FED_FUNDS_RATE | Fed funds rate |
| SOFR | Secured overnight rate |
| US_CPI | CPI all urban |
| US_ISM_MFG | ISM manufacturing |
| US_UNEMPLOYMENT | Unemployment rate |

## When to use

- Macro agent: check WTI, DXY, yield curve, and credit before every proposal
- All agents: check VIX and HY spread for risk-on/risk-off regime
- Always cite specific levels and changes in proposals
