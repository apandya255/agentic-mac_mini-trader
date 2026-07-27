# agentic-mac_mini-trader
A multi-agent AI system that continuously screens ~500 equities, 11 sector ETFs, 20 country ETFs, and key commodities to generate hedged long/short trade recommendations.

# Agentic AI Trading System — Executive Brief

---

## What It Is

A multi-agent AI system that continuously screens ~500 equities, 11 sector ETFs, 20 country ETFs, and key commodities to generate hedged long/short trade recommendations. Twenty-one specialized agents — fundamental analysts, macro strategists, technical traders, a risk manager, and a portfolio manager — operate within a structured debate and approval pipeline. Every output is advisory; a human makes the final execution decision.

---

## How It Works

```
Fundamental & Macro agents screen universe continuously
        ↓
Agent identifies opportunity → publishes thesis with conviction score
        ↓
Other agents debate (adversarial, evidence-based, 2-3 rounds)
        ↓
Technical agent scores the setup (entry, stops, levels)
        ↓
Risk agent gates: factor betas, concentration, drawdown budget
        ↓
PM agent sizes, sets parameters, delivers recommendation
        ↓
Human reviews and executes discretionarily
```

---

## Why Build It

| Problem | Solution |
|---------|----------|
| Attention budget — can't screen 500 names daily | 21 agents running continuously, never fatigued |
| Style drift under pressure | Risk rules enforced structurally, not behaviorally |
| Missed overnight catalysts | Agents process events as they happen, propose by morning |
| Cognitive biases (anchoring, loss aversion) | Agents debate adversarially, forced to cite evidence |
| Single-analyst blind spots | Cross-agent debate surfaces variant views |

---

## Key Design Principles

1. **Every bet is hedged** — single names vs. equal-weight sector ETF, sector ETFs vs. RSP, country ETFs vs. DM/EM broad index
2. **Factor-neutral discipline** — book never exceeds ±0.6 beta to DXY, SPX, rates, VIX, oil, credit, gold, growth/value, large/small
3. **Dynamic leverage** — scales with P&L and correlation regime (higher when winning + uncorrelated)
4. **Advisory only** — no auto-execution, preserves discretionary overlay
5. **Audit trail** — every thesis, debate, score, and decision is logged and reviewable

---

## Performance Targets & Risk Envelope

| Metric | Target |
|--------|--------|
| Annualized return | 12–15%+ |
| Downside volatility | ≤6% |
| Position stop-loss | 2–3% |
| Position target | 5% |
| Max factor beta | ±0.6 |
| Implied Sharpe | ≥2.0 |

---

## Agent Composition

- **11 Fundamental agents** — one per GICS sector, bottom-up L/S equity analysis
- **6 Macro agents** — LatAm, CEEMEA, Asia, North America, Western Europe, Commodities
- **2 Technical agents** — equity/ETF technicals + commodity-specific
- **1 Risk Management agent** — factor betas, correlation, drawdown, leverage
- **1 Portfolio Management agent** — final sizing, entry, stops, book construction

---

## Cost & Infrastructure

| Item | Estimate |
|------|----------|
| Monthly run cost | ~$750 (LLM APIs + data feeds) |
| Hardware | Personal server (Mac Studio or equivalent) |
| Access | Tailscale VPN — secure read-only from any device |
| Development timeline | ~30 weeks to full production (POC in 4-6 weeks) |

---

## What We Need to Decide

1. Risk parameters — are ±0.6 factor limits and 6% downside vol correct for this strategy?
2. Leverage operating range — what's the real comfort zone?
3. Data priority — which feeds matter most early on?
4. Interaction preference — email digest? Dashboard? Both?
5. Hedge instrument preferences — any overrides to the default mapping?

---

*This system augments discretionary judgment with structured, tireless research. It doesn't replace the PM — it gives the PM better raw material, faster.*

