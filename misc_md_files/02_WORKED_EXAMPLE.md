# Worked Example: End-to-End Trade Pipeline

*This walkthrough shows exactly how a single trade idea moves from inception to recommendation delivery, with realistic (illustrative) data.*

---

## The Setup

**Date:** Tuesday morning, 6:30 AM ET  
**Context:** OPEC+ announced an unexpected 500k bbl/d production cut overnight. WTI crude jumps 4% in Asian trading.

---

## Stage 1: Idea Generation

### Agent: `macro_commodities`

The Commodities macro agent processes the overnight news during its 6:30 AM cycle. It updates its beliefs:

> **Belief update:** OPEC+ supply discipline stronger than consensus expected. With China PMIs stabilizing and US SPR still depleted, S/D balance tightening faster than market is pricing. Brent forward curve was in mild contango — expect shift toward backwardation.

**Proposal published:**

| Field | Value |
|-------|-------|
| Ticker | XLE (Energy Select Sector ETF) |
| Direction | Long |
| Hedge | Short RSP (equal-weight S&P 500) |
| Thesis | OPEC+ cut tightens S/D into a market already underestimating demand recovery. Energy equities under-owned after 6-month rotation into tech. XLE trades at 10.5x forward P/E vs. 5-year avg of 12.8x. |
| Conviction | 8/10 |
| Target | +5% (sector re-rate as oil stabilizes above $85) |
| Stop | -2.5% |
| Time horizon | 4-8 weeks |

---

## Stage 2: Debate

### Round 1 — Challenges

**`fund_energy` (Energy Fundamental Agent):**
> **Stance: Support** — Agree with the setup. My bottom-up work confirms energy names are cheap. XOM at 11.2x, CVX at 10.8x, both below 5-year averages despite improved capital discipline. Shareholder return yields (buyback + dividend) averaging 7.2% across the top 5 names. Sector positioning per 13F data is 2 standard deviations below 3-year average.
>
> *Would add:* Consider expressing via single-name (XOM) for more alpha, but XLE works for speed.

**`macro_north_america` (North America Macro Agent):**
> **Stance: Challenge** — Concern: if oil spikes too far too fast ($90+), the Fed hawkishness narrative returns. DXY strengthens, real rates re-price higher, and energy equities sell off *despite* the commodity rallying. We saw this dynamic in Q3 2023. Additionally, US gasoline demand is seasonally peaking — watch for demand disappointment post-summer.
>
> *Revised conviction if I were proposing:* 6/10. The asymmetry isn't as clean as it looks.

**`fund_technology` (Technology Fundamental Agent):**
> **Stance: Neutral** — No direct view on energy fundamentals, but flagging that if this trade works, it may correlate with a risk-on rotation out of tech. Our current book has a long MSFT position via `fund_technology`. Factor correlation between XLE long and MSFT long is -0.3 — actually diversifying. No objection.

---

### Round 2 — Originator Response

**`macro_commodities` responds to `macro_north_america`:**
> Acknowledge the Fed risk but disagree it's the base case here. The cut is 500k bbl/d, not 2M — this takes oil to $82-87, not $95. That's the sweet spot for energy equities (high enough for margins, not high enough to trigger macro blowback). On seasonality: yes, gasoline peaks, but distillate demand is the swing factor into Q4, and inventories are at 5-year lows.
>
> **Conviction holds at 8/10.** The macro_north_america challenge is the tail risk, not the base case.

---

### Round 3 — Final Assessment

**`macro_north_america`:**
> Fair point on magnitude. $82-87 is not the danger zone. Withdrawing the challenge — I'd move to **neutral/mild support** at this level. If oil breaks above $90 before the position target is hit, that's when I'd flag for review.

**Debate outcome:** Conviction 8/10, no withdrawal. Proceed to technical scoring.

---

## Stage 3: Technical Scoring

### Agent: `tech_equity`

| Field | Assessment |
|-------|-----------|
| **Technical score** | 7/10 |
| **Trend** | XLE above rising 50-day MA ($88.42), above 200-day ($85.10). Trend aligned. |
| **Momentum** | RSI at 58 — not overbought, room to run. MACD just crossed bullish. |
| **Volume** | Today's pre-market volume 2.3x average — confirms institutional interest on the news. |
| **Key support** | $87.50 (50-day MA), $85.00 (200-day MA), $83.20 (March low) |
| **Key resistance** | $93.80 (January high), $96.00 (2024 high) |
| **Fibonacci** | 61.8% retracement of Jan-to-March decline sits at $92.40 |
| **CTA context** | Systematic trend followers currently short energy — a break above $91 triggers CTA buy programs (estimated $2-3B flow). Potential accelerant. |
| **Options** | Put/call ratio on XLE dropped from 1.4 to 0.8 overnight — sentiment shifting. 30-day implied vol at 22% vs. 18% realized — slight premium but not stretched. |

**Suggested levels:**
- Entry: $89.50 (current level, market on open)
- Stop-loss: $86.80 (below 50-day MA — gives 3% room)
- Take-profit: $94.00 (just below Jan high — achievable within timeframe)
- Trailing stop: 2x ATR below (currently ATR = $1.20, so trail at $2.40 below price)

**Timing:** Now. Volume confirmation + catalyst + trend alignment = don't wait.

---

## Stage 4: Risk Gate

### Agent: `risk_management`

**Pre-trade book state:**
- Current NAV: $10,000,000
- Gross leverage: 1.4x
- Net exposure: +0.15
- Positions: 8 active (4 long, 4 short)
- Factor betas (current): DXY -0.12, SPX +0.18, USGG10Yr -0.05, VIX -0.22, CL1 +0.08, XAU +0.10

**Projected impact of adding Long XLE / Short RSP at 2% NAV:**

| Factor | Current Beta | Projected Beta | Limit | Status |
|--------|-------------|---------------|-------|--------|
| DXY | -0.12 | -0.10 | ±0.6 | ✅ OK |
| SPX | +0.18 | +0.16 | ±0.6 | ✅ OK (RSP short offsets) |
| USGG10Yr | -0.05 | -0.04 | ±0.6 | ✅ OK |
| VIX | -0.22 | -0.24 | ±0.6 | ✅ OK |
| CL1 | +0.08 | +0.19 | ±0.6 | ✅ OK |
| Growth/Value | +0.05 | -0.02 | ±0.6 | ✅ OK (energy is value) |
| Large/Small | +0.03 | +0.02 | ±0.6 | ✅ OK |
| CDX HY 5Y | -0.08 | -0.06 | ±0.6 | ✅ OK |
| XAU | +0.10 | +0.12 | ±0.6 | ✅ OK |

**Additional checks:**
- Projected gross leverage: 1.44x → ✅ within regime (positive P&L, low correlation: 1.5-2.5x allowed)
- Correlation to existing positions: max 0.35 (to long materials position) → ✅ below 0.7 threshold
- Sector concentration: Energy would move from 0% to 2% gross → ✅ well below 25% limit
- Stop-loss at 3.0% → ✅ within 2-3% guideline (at outer edge — acceptable for 8/10 conviction)

**Risk Decision: APPROVED**

> No modifications required. Position fits the book cleanly — low correlation to existing positions, all factors well within limits, leverage appropriate for current regime. CL1 beta moves from +0.08 to +0.19 — still comfortable but will be watching. If oil spikes and CL1 beta approaches +0.4, will flag for review.

---

## Stage 5: PM Decision

### Agent: `portfolio_management`

**Synthesis:**
- Conviction: 8/10 (held through debate)
- Technical score: 7/10 (trend aligned, momentum favorable, CTA accelerant potential)
- Risk: approved without modification
- Correlation to book: low (0.35 max)
- Current regime: positive P&L month, low inter-position correlation → green light for normal sizing

**Sizing calculation:**
- Base size: 2.0% NAV
- Conviction scalar (8/10): 1.0x → 2.0%
- Technical adjustment (7/10): 1.0x → 2.0%
- Correlation penalty: none (below 0.5 threshold)
- **Final size: 2.0% NAV ($200,000 notional per leg)**

**Trade Order:**

```
═══════════════════════════════════════════════════════
          TRADE RECOMMENDATION
═══════════════════════════════════════════════════════

Date:       Tuesday, 1:45 PM ET
Priority:   NORMAL
Source:     macro_commodities → debated → scored → approved

PRIMARY LEG
  Action:   BUY
  Ticker:   XLE
  Size:     2.0% NAV ($200,000)
  Entry:    Market (current ~$89.50)
  Stop:     $86.80 (-3.0%)
  Target:   $94.00 (+5.0%)
  Trail:    2x ATR ($2.40 below price, adjust daily)

HEDGE LEG
  Action:   SELL SHORT
  Ticker:   RSP
  Size:     2.0% NAV ($200,000)
  Entry:    Market (current ~$164.20)

TIME HORIZON: 4-8 weeks
REVIEW DATE: 2 weeks from entry (reassess if no movement)

THESIS: OPEC+ 500k cut tightens S/D into under-owned, 
cheap energy sector. Sweet-spot oil ($82-87) supports 
margins without triggering macro blowback. CTA short 
positioning = potential squeeze above $91.

KEY RISK: Oil overshoots $90+ → Fed narrative returns.
Monitor CL1 beta (currently +0.19 projected).

DEBATE SUMMARY: Supported by fund_energy (cheap names, 
low positioning). Challenged by macro_north_america on 
Fed risk — rebutted on magnitude (500k not 2M). Challenge 
withdrawn. Consensus: favorable setup.

═══════════════════════════════════════════════════════
```

---

## Stage 6: Delivery

- **1:45 PM ET** — Trade order email sent to operator
- **1:45 PM ET** — Dashboard updated (new position in "pending" state)
- **Operator reviews** — decides whether to execute
- **If executed** — operator marks as filled in dashboard, position moves to "active"
- **Ongoing** — Risk agent monitors stop/target daily; technical agent updates trailing stop

---

## What Happens Next

| Day | Event |
|-----|-------|
| Day 1-3 | XLE moves to $90.80 (+1.5%). RSP flat. P&L: +$3,000 |
| Day 7 | Oil settles at $84. XLE at $91.50 (+2.2%). Trailing stop adjusts to $89.10 |
| Day 14 | Review date. Technical agent confirms momentum holding. PM extends hold. |
| Day 21 | CTA buy programs trigger as XLE breaks $91. Volume surges. XLE moves to $93.20 (+4.1%) |
| Day 28 | XLE hits $94.00 — **target reached**. PM takes 50% profit ($100K leg). Trails remainder. |
| Day 35 | Remaining position stopped at $92.40 (trailing stop). Final P&L on remainder: +3.2% |

**Total trade P&L:**
- First half: +5.0% × $100K = +$5,000
- Second half: +3.2% × $100K = +$3,200
- Hedge leg (RSP short): -0.8% × $200K = -$1,600 (market drifted up slightly)
- **Net P&L: +$6,600 on $200K risk (3.3% return in 5 weeks)**

---

*This is one trade through the full pipeline. The system runs 21 agents across 500+ names simultaneously, potentially surfacing 3-5 ideas per day for review.*
