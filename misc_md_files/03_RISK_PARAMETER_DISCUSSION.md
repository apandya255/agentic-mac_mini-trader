# Risk Parameter Discussion Sheet

*These are the proposed defaults. Each is a question for the partner, not a declaration. The goal of this conversation is calibration — aligning the system's risk envelope to his actual comfort level and experience.*

---

## 1. Factor Beta Limits

**Current default:** ±0.6 to any individual factor

**Factors tracked:**

| Factor | Proxy | Why We Track It |
|--------|-------|-----------------|
| DXY | US Dollar Index | Dollar strength hits EM, commodities, multinationals |
| SPX | S&P 500 | Market beta — are we net long/short equities? |
| USGG10Yr | US 10-Year Yield | Duration/rate sensitivity |
| VIX | CBOE Vol Index | Volatility regime exposure |
| Growth/Value | R1000G / R1000V | Style factor — crowded trades blow up on rotation |
| CL1 | WTI Front Month | Energy/commodity beta |
| Large/Small | R1000 / R2000 | Cap factor — liquidity risk in stress |
| CDX HY 5Y | HY Credit Spread | Credit cycle exposure |
| XAU | Gold Spot | Safe-haven / real rate sensitivity |

**Questions for discussion:**

- Is ±0.6 the right tolerance? Some systematic funds run ±0.3 (tighter) while discretionary macro may accept ±1.0 on conviction trades.
- Should some factors have tighter limits than others? (e.g., SPX at ±0.4 if the goal is truly market-neutral, but CL1 at ±0.8 if energy is a core competency)
- Are there factors missing? Candidates: CNY (China risk), MOVE index (rates vol), sector momentum factor, EM risk premium.
- How is beta computed at Graham? Rolling 12-month univariate OLS is our default — is there a preferred methodology (multivariate, shorter window, exponential weighting)?
- What's the rebalancing trigger? Do we act when a factor hits 0.5 (approaching), or only at the 0.6 breach?

---

## 2. Position-Level Risk

**Current defaults:**

| Parameter | Default | Range to Discuss |
|-----------|---------|------------------|
| Stop-loss | 2–3% per position | 1.5% (tighter) to 4% (wider for high-conviction) |
| Gain target | 5% per position | 4% (faster turnover) to 8% (let winners run) |
| Max single position | 5% NAV | 3% (conservative) to 7% (concentrated) |
| Max sector gross | 25% NAV | 15% to 30% |
| Max country gross | 15% NAV | 10% to 20% |

**Questions for discussion:**

- **Stop-loss philosophy:** Fixed percentage? ATR-based (volatility-adjusted)? Technical level (below support)? Or a combination — whichever is hit first?
- **Should conviction modulate stop width?** e.g., 8/10 conviction gets a 3% stop, 6/10 gets 2%? Or is discipline uniform?
- **Gain targets:** Take full profit at 5%? Or partial (50% at target, trail the rest)? The worked example uses the partial approach — is that preferred?
- **Time stops:** If a position hasn't moved in 30/45/60 days, do we exit or reassess? What's the right number?
- **Sizing:** Is 2% NAV base size appropriate? With conviction scaling up to 3% for 10/10 ideas? Or should the range be narrower (1.5%–2.5%)?

---

## 3. Leverage Framework

**Current default regime model:**

| Regime | Conditions | Leverage Range |
|--------|-----------|----------------|
| Aggressive | Positive P&L + low correlation | 1.5x – 2.5x gross |
| Normal | Positive P&L + moderate correlation | 1.0x – 1.5x gross |
| Cautious | Negative P&L + low correlation | 0.8x – 1.2x gross |
| Defensive | Negative P&L + high correlation | 0.3x – 0.8x gross |

**Questions for discussion:**

- What's the actual operating range you're comfortable with? Is 2.5x ever appropriate, or is 1.8x the real ceiling?
- How do you define "positive P&L" — MTD? Trailing 20 days? Since last drawdown recovery?
- What correlation threshold separates "low" from "high"? We've defaulted to 0.4 average pairwise — is that right?
- Should leverage be discretionary (PM agent decides within range) or mechanical (formula-driven based on metrics)?
- Net exposure: is the target truly ±0.3 (near market-neutral) or is there tolerance for ±0.5 on high-conviction directional views?

---

## 4. Drawdown Management

**Current default waterfall:**

| Drawdown from Peak | Action |
|--------------------|--------|
| 0% – 2% | Normal operations |
| 2% – 3% | Review lowest-conviction positions; reduce sizing 20% |
| 3% – 4% | Mandatory deleverage to 50% gross; halt new positions |
| 4%+ | Emergency deleverage to 30%; joint PM + Risk review |
| Recovery | Re-lever only after 5 consecutive positive days |

**Questions for discussion:**

- Are these thresholds calibrated correctly for a 6% vol target? (4% drawdown = 0.67 sigma event at 6% vol — should we trigger earlier?)
- Is "5 consecutive positive days" the right re-engagement rule? Or is it too rigid / too loose?
- At 4%+ drawdown, does the system go fully flat (close everything) or just reduce? What's the "pull the plug" level?
- Should there be an annual drawdown budget? (e.g., "if we're down 6% YTD, shut down until next quarter")
- Who makes the final call in a drawdown — the Risk agent mechanically, or the human operator?

---

## 5. Hedging Parameters

**Current defaults:**

| Trade Type | Hedge Instrument | Hedge Ratio |
|------------|-----------------|-------------|
| Single name | Equal-weight sector ETF | 1:1 dollar-neutral |
| Sector ETF | RSP (EW S&P 500) | 1:1 dollar-neutral |
| DM country ETF | EFA or ACWI | 1:1 dollar-neutral |
| EM country ETF | EEM or ACWI | 1:1 dollar-neutral |
| Commodity | PM discretion | Varies |

**Questions for discussion:**

- **Dollar-neutral vs. beta-neutral:** Should we adjust the hedge ratio for beta? (e.g., if XOM has 1.2 beta to RSPG, short 1.2x RSPG to be truly beta-hedged?)
- **Equal-weight ETF availability:** Some sectors don't have liquid equal-weight ETFs. Acceptable to use cap-weighted? Or build a custom basket?
- **Country ETF hedging:** DM ideas → EFA vs. ACWI — is there a preference? Does it depend on the region?
- **Commodity hedging:** This is the loosest rule. Should there be a default (e.g., always hedge gold with ACWI) or is PM discretion correct here?
- **Hedge slippage:** In practice, the hedge may not perfectly offset. How much residual beta is acceptable? (e.g., ±0.15 on the hedge leg?)

---

## 6. Correlation & Concentration

**Current defaults:**

| Parameter | Default |
|-----------|---------|
| Max pairwise correlation between positions | 0.7 |
| Crowded cluster threshold | 3+ positions with avg correlation > 0.6 |
| Crowded cluster max size | 15% NAV gross |
| Book avg pairwise correlation alert | > 0.4 |

**Questions for discussion:**

- Are these the right thresholds? In practice, energy names are all 0.6-0.8 correlated to each other — does that mean only one energy single-name at a time?
- Should we distinguish between intra-sector correlation (expected, acceptable) and cross-sector correlation (dangerous, signals hidden factor exposure)?
- How often should the correlation matrix update? Daily (60-day rolling)? Or shorter window (20-day) to catch regime shifts faster?

---

## 7. What I'd Like Your Input On

To summarize, the key decisions I need your guidance on:

1. **Factor limits:** ±0.6 across the board, or differentiated?
2. **Stop philosophy:** Fixed %, ATR-based, or technical?
3. **Leverage ceiling:** 2.5x? 2.0x? 1.5x?
4. **Drawdown triggers:** Are the waterfall levels right?
5. **Hedge ratio:** Dollar-neutral or beta-adjusted?
6. **Net exposure tolerance:** ±0.3 or wider?
7. **Missing factors or constraints?**

These parameters are the system's operating manual — getting them right means the AI risk manager enforces *your* risk appetite, not a generic one.

---

*All parameters are configurable and can be adjusted over time as we see how the system performs. The POC will run with whatever we agree on today, and we'll iterate based on live results.*
