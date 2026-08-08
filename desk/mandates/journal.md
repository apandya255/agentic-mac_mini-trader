# Trade Journal — desk/journal.md

The audit record. Every book action gets an entry the moment it happens — entries, exits, trail cuts, target decisions, adjustments, conviction upgrades. positions.md shows the position as a level; the journal shows the legs, the fills, and the reasoning. Append-only; never edited after the fact.

## Entry schema (one block per action)

```
[YYYY-MM-DD HH:MM ET] #position — ACTION (OPEN / ADD / TRIM / TRAIL CUT / TARGET TAKE / TARGET EXTEND / THESIS-BREAK CLOSE)
Instrument: LONG XLE/RSP @ 0.5234 | Wts 1:1 | Size 3.2% NAV | Tier: standard
Leg fills (net of slippage): XLE 94.12 (2bps) / RSP 179.85 (2bps)
Thesis: ≤2 lines
Flip-condition: the falsifiable line
Trail: 2.5% | Target: +5% | Loss-at-trail: 8bps NAV
Factor deltas at action: only those >|0.1|
Debate record: originating seat / rebuttal seat (model families) / Technical score / Risk verdict
Rationale: why now, why this size — for adjustments and extensions, the debated justification
```

On CLOSE actions add: exit level and leg fills, P&L (% and $), days held, peak reached, trail slippage (level vs. observed fill) — and write the one process lesson to desk/lessons.md.

| — journal begins below — |
