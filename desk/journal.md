# Trade Journal — desk/journal.md

The audit record. Every book action gets an entry the moment it happens. Append-only; never edited after the fact.

## Entry schema
[YYYY-MM-DD HH:MM ET] #position — ACTION
Instrument: LONG ticker/hedge @ ratio | Wts 1:1 | Size X% NAV | Tier: standard
Leg fills: ticker $X / hedge $Y
Thesis: (from portfolio_thesis)
Flip-condition: trail breach or thesis break
Trail: 2.5% | Target: +5%
Rationale: (from pm_rationale)

---

| — journal begins below — |

[2026-07-28 00:07 ET] #1 — OPEN
Instrument: LONG XOM/RSPG @ 1.4788 | Wts 1:1 | Size 4.0% NAV | Tier: standard
Leg fills: XOM $154.77 / RSPG $104.66
Thesis: Inaugural position. Single-name energy alpha hedged with EW sector ETF. Low correlation to empty book. Catalyst-driven with defined 4-week timeline.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-10
Rationale: Strong setup: conviction 8/10 held through debate (macro supported), technical score 8/10 bullish, risk approved at full size. Empty book — this is the inaugural trade. XOM offers best risk/reward in the sector (cheapest integrated on EV/EBITDA with strongest capital return). Catalyst in 4 weeks provides natural timeline.

[2026-07-28 13:44 ET] #2 — OPEN
Instrument: LONG NFLX/RSPC @ 2.0274 | Wts 1:1 | Size 3.0% NAV | Tier: standard
Leg fills: NFLX $73.38 / RSPC $36.19
Thesis: NFLX presents compelling contrarian value at 96th percentile oversold vs sector pair, trading 19.2x forward P/E at trough levels with 29% analyst upside target. Technical momentum building above key support levels.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-25
Rationale: Diversification trade: NFLX long provides commsvcs sector exposure. Conviction 7/10. Book currently concentrated in energy only.

[2026-07-28 13:44 ET] #3 — OPEN
Instrument: LONG BKNG/RSPD @ 3.4394 | Wts 1:1 | Size 4.0% NAV | Tier: standard
Leg fills: BKNG $197.32 / RSPD $57.37
Thesis: BKNG offers compelling long opportunity with travel recovery momentum accelerating, strong technical setup, and attractive valuation vs. growth profile.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-25
Rationale: Diversification trade: BKNG long provides consdisc sector exposure. Conviction 8/10. Book currently concentrated in energy only.

[2026-07-28 13:44 ET] #4 — OPEN
Instrument: LONG WMT/RSPS @ 3.5908 | Wts 1:1 | Size 3.0% NAV | Tier: standard
Leg fills: WMT $113.54 / RSPS $31.62
Thesis: WMT oversold relative to staples peers despite strong fundamentals. Trading at 22% discount to analyst consensus with pair ratio at 22nd percentile of 52-week range.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-25
Rationale: Diversification trade: WMT long provides consstaples sector exposure. Conviction 7/10. Book currently concentrated in energy only.

[2026-07-28 13:44 ET] #5 — OPEN
Instrument: LONG DVN/RSPG @ 0.4129 | Wts 1:1 | Size 3.0% NAV | Tier: standard
Leg fills: DVN $42.61 / RSPG $103.20
Thesis: DVN offers exceptional value in E&P space, trading at 0th percentile vs peers on EV/EBITDA (5.0x) and forward PE (8.1x) with 39% analyst upside target. Pair ratio at extreme oversold levels (0.8th percentile, z-score -2.02) vs equal-weight energy, suggesting strong mean-reversion opportunity.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-25
Rationale: Diversification trade: DVN long provides energy sector exposure. Conviction 7/10. Book currently concentrated in energy only.

[2026-07-28 13:44 ET] #6 — OPEN
Instrument: LONG V/RSPF @ 4.3602 | Wts 1:1 | Size 4.0% NAV | Tier: standard
Leg fills: V $368.79 / RSPF $84.58
Thesis: Visa offers best risk/reward in Financials - secular payments growth, defensive moats, trading 9% below analyst targets with strongest technicals in coverage universe.
Flip-condition: trail breach -2.5% from peak or thesis break
Trail: 2.5% | Target: +5% | Review: 2026-08-25
Rationale: Diversification trade: V long provides financials sector exposure. Conviction 8/10. Book currently concentrated in energy only.
