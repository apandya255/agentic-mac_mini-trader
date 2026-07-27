# Anticipated Questions & Prepared Answers

*Organized by likely order of conversation — starting with "what is this" and progressing to skeptical/detailed pushback.*

---

## The Basics

### "Walk me through what this actually does."

> Twenty-one AI agents — each one acting like a specialized analyst or PM — continuously screen our universe of S&P 500 names, sector ETFs, country ETFs, and commodities. When one of them finds an opportunity, it writes up a thesis and proposes a hedged trade. Other agents challenge the idea in a structured debate. If it survives debate, a technical agent scores the setup, a risk agent checks it against our limits, and a PM agent sizes it and sends us the recommendation. We review it and decide whether to execute. Nothing auto-trades.

### "So it's a quant screen with extra steps?"

> No. A quant screen ranks stocks on factors and spits out a list. This system *reasons*. Each agent builds a thesis — "XOM is cheap because the market is mispricing their Permian breakeven at $45 when it's actually $38, and the coming OPEC cut will tighten the S/D balance." Then another agent challenges that: "But if oil goes above $90, the Fed narrative returns and energy sells off." The originator has to respond with evidence. That adversarial process is the difference — it's closer to an investment committee than a screen.

### "Why not just use ChatGPT and ask it for trade ideas?"

> Three reasons. First, a single chat session has no memory — it forgets your book, your risk limits, your prior trades. This system persists beliefs and evolves them as new data comes in. Second, there's no risk enforcement in a chat — you can ask for ideas all day and it'll happily give you levered, correlated, unhedged positions. Our system structurally rejects anything that breaches factor limits. Third, scale — you can't run 21 simultaneous analysts in a chat window, each with their own specialization, debating each other, and maintaining independent views.

---

## The Edge

### "Where's the alpha in this?"

> The alpha isn't in the AI being smarter than a human analyst on any single name. It's in three structural advantages:
>
> 1. **Coverage breadth.** No human team can run deep fundamental models on 500 names simultaneously and also track macro across 6 regions. The system never sleeps, never gets distracted, never has a bad day.
>
> 2. **Process discipline.** Every idea gets debated, technically scored, risk-checked, and sized by formula. No style drift, no anchoring, no "I'll just hold a little longer." The risk rules are enforced mechanically.
>
> 3. **Speed to conviction.** An overnight OPEC cut happens at 2 AM — by 7 AM the macro agent has a thesis, the energy fundamental agent has confirmed the single-name implications, and you have a sized trade recommendation before the open. A human team gets there by lunch.

### "Aren't LLMs just pattern-matching on training data? How do they generate real insight?"

> Fair concern. Two things: First, the agents aren't operating in a vacuum — they're fed real-time data (prices, estimates, filings, macro releases). The LLM provides the analytical framework and reasoning; the data provides the edge. The agent's job is to interpret fresh data through a sector-specific lens and identify where consensus is wrong.
>
> Second, the debate protocol is the quality filter. If an agent hallucinates a thesis that doesn't hold up, another agent will challenge it. Bad ideas get killed in debate — that's the design. We're not trusting any single LLM output; we're trusting the *process*.

### "What's the win rate going to be?"

> Honest answer: we don't know yet. But the system is designed for a 55-60% hit rate with asymmetric payoffs (5% target vs. 2-3% stop = ~2:1 reward/risk). At 55% win rate with 2:1 R/R, the math works to the 12-15% target. We'll track per-agent performance and can dial down or retrain agents that underperform.

---

## Skepticism & Pushback

### "LLMs hallucinate. How do you trust a hallucinating model with trade decisions?"

> We don't. The system has four layers of defense:
>
> 1. **Structured output validation** — every agent output is parsed against a strict schema. If it references a ticker that doesn't exist, proposes a position without a hedge, or outputs nonsensical numbers, it's rejected and retried.
>
> 2. **Adversarial debate** — other agents challenge the thesis. A hallucinated thesis won't survive two rounds of evidence-based scrutiny from agents looking at real data.
>
> 3. **Risk gate** — even if a bad idea somehow survives debate, the risk agent applies quantitative checks (factor betas, concentration limits) that don't require "understanding" the thesis, just math.
>
> 4. **Human final decision** — nothing auto-executes. You read the recommendation, read the debate transcript, and decide. The system is a research tool, not an execution engine.

### "What happens when all 21 agents get the same thing wrong?"

> That's the correlated error scenario — essentially model bias. Three mitigants:
>
> 1. **Agents are specialized differently.** The energy fundamental agent looks at breakevens and reserves; the macro commodities agent looks at OPEC policy and S/D. They use different data and different frameworks. Correlated error requires all of them to fail simultaneously on different axes.
>
> 2. **The risk framework is model-agnostic.** Factor beta limits don't care *why* the agents are bullish — if the book gets too long oil, the risk agent blocks new additions regardless of thesis quality.
>
> 3. **The human is the final filter.** If all 21 agents are pounding the table on one direction and it feels wrong to you, you don't trade it. The system surfaces ideas; it doesn't compel action.

### "This sounds expensive. What's the ROI math?"

> Monthly run cost is ~$750 (LLM APIs + data feeds). On a $10M book targeting 12-15%, you need $1.2-1.5M in annual returns. The system costs $9K/year — it needs to generate 0.09% of alpha to break even. One good trade pays for a year of operation. The real question isn't cost; it's whether the incremental coverage and discipline generate even marginal alpha above what you'd do alone.

### "What if the market regime changes and the models are stale?"

> The agents aren't static models — they're reasoning engines fed live data. When the regime shifts, the data shifts, and the agents' conclusions shift. The macro agents explicitly track regime (risk-on/off, inflation/deflation, tight/easy policy) and adjust their frameworks. The risk agent adjusts leverage based on realized correlation and P&L regime.
>
> That said, the *prompts* (the analytical frameworks) may need updating over time. If we find that an agent's framework doesn't adapt to a new regime (e.g., a post-AI-productivity world where old valuation metrics don't work), we revise the prompt. That's a quarterly maintenance task, not a fundamental flaw.

### "Graham runs systematic strategies. How is this different from what we already do?"

> This isn't systematic in the traditional sense — there's no backtest, no optimized parameters, no signal decay analysis. It's closer to discretionary macro enhanced by AI. The key differences from a systematic approach:
>
> - No historical backtest (LLM reasoning can't be backtested in the traditional sense)
> - Human-in-the-loop on every trade
> - Theses are narrative, not purely quantitative
> - Position holding periods are flexible, not mechanical
>
> Think of it as a complement, not a replacement. It occupies the discretionary alpha space that systematic can't reach — variant perception, catalyst identification, cross-asset thematic connections — but with the risk discipline you'd expect from a systematic shop.

---

## Implementation & Logistics

### "How long until this is live?"

> POC (proving the pipeline works end-to-end on a small subset): 4-6 weeks. Full production with all 21 agents: ~30 weeks. We can start generating real recommendations from the POC subset (Energy + Commodities) within 2 months while building out the rest.

### "What do you need from me?"

> Four things:
> 1. **Risk parameter calibration** — the discussion sheet I've prepared. 30 minutes to align on limits, leverage, stops.
> 2. **Investment process validation** — are there edge cases or rules we're missing? Ways you think about trade construction that aren't captured?
> 3. **Data source priorities** — if we can only have one paid data feed to start, which matters most?
> 4. **Ongoing feedback** — once it's running, telling me which recommendations make sense and which don't, so we can tune the agents.

### "Where does this run? What about compliance?"

> On a personal device (likely a Mac Studio at home), completely outside the firm ecosystem. No firm data goes in; no firm systems are touched. Access is via encrypted private network (Tailscale) — I can read the dashboard from my phone but nothing connects to firm infrastructure. Output is trade *ideas* only — I'd execute manually in my personal account or PA account.

### "What if you leave or this breaks?"

> Everything is documented — the framework spec, the design doc, the agent prompts. The system runs on standard open-source tools (Python, PostgreSQL, Redis). If I get hit by a bus, someone with moderate Python experience can maintain it. It also degrades gracefully — if the system goes down, positions have stops that execute at the broker level regardless.

---

## Technical Depth (If He Goes There)

### "Why Claude/GPT-4 and not a fine-tuned model?"

> Fine-tuning requires thousands of examples of "good trade ideas" with labeled outcomes — we don't have that dataset, and the sample size of macro trades is inherently small. Frontier models (Claude, GPT-4) have broad financial knowledge out of the box and excel at reasoning tasks. The edge comes from the *system design* (specialization, debate, risk enforcement), not from model training. We may fine-tune later once we have a track record of which agent outputs led to good trades.

### "How do you prevent the agents from all converging to the same view?"

> Three mechanisms:
> 1. **Different data inputs.** The energy agent sees micro data (rig counts, refining margins); the macro agent sees macro data (OPEC policy, global S/D). They form views independently.
> 2. **Independent memory.** Each agent maintains its own beliefs, updated from its own track record. An agent that got burned being long energy last quarter will be more cautious, even if another agent is bullish.
> 3. **Debate structure.** Agents are incentivized (via prompt design) to challenge, not agree. The system rewards intellectual honesty and penalizes groupthink.

### "What's the latency? Can it react to news intraday?"

> An event-driven trigger (earnings release, central bank decision) activates the relevant agent within minutes. A full proposal-through-pipeline cycle takes 5-15 minutes (depending on debate rounds). This is designed for daily/weekly positioning, not high-frequency. If an overnight event changes the landscape, you have a recommendation by pre-market open. We're not competing with algos on speed; we're competing with human analysts on depth and coverage.

---

## Closing / If He's Interested

### "What's the next step?"

> I'd like to:
> 1. Lock in the risk parameters today based on your feedback
> 2. Build the POC over the next 4-6 weeks (Energy sector + Commodities as the test case)
> 3. Run it in "paper" mode — generating recommendations but not trading — for 2-4 weeks so you can evaluate quality
> 4. If the output looks credible, expand to full universe over the following 3-4 months
>
> The first real deliverable you'd see is: a daily email with 1-3 hedged trade ideas, each with a full thesis, debate summary, technical score, and risk clearance. You read them over coffee and decide which ones you like.

---

*Read the room. If he's engaged and asking technical questions, go deep. If he's checking his phone, get to the worked example fast — it makes everything concrete.*
