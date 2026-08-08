# Policy Rates — desk/rates_table.md

Maintained by the macro seats as a byproduct of the daily sweep; each seat owns its currencies' rows. Feeds: FX carry accrual (carry.py reads this file), CB-decision interrupts (next-meeting dates), and the calendar. A stale row corrupts carry P&L silently — every sweep verifies its rows' "as of" against the CB's own site; any change same-day.

Conventions: rate = the announced policy rate in %, upper bound where a corridor/range is announced (Fed = upper bound of the target range). "Next" = next scheduled decision date (ET date). Rows exist for every currency with an open FX position PLUS the standing set below; a new pair entering the book adds its legs' rows before the fill.

| CCY | Policy rate % | As of (last change) | Next decision | CB | Owner seat |
|-----|---------------|---------------------|---------------|-----|------------|
| USD | 4.25-4.50 | 2026-06-18 | 2026-07-30 | Fed | North America |
| EUR | 3.65 | 2026-06-05 | 2026-07-17 | ECB | Western Europe |
| JPY | 0.50 | 2026-03-14 | 2026-07-31 | BoJ | Asia |
| GBP | 4.25 | 2026-06-19 | 2026-08-07 | BoE | Western Europe |
| CHF | 0.25 | 2026-06-19 | 2026-09-18 | SNB | Western Europe |
| CAD | 3.75 | 2026-06-04 | 2026-07-30 | BoC | North America |
| AUD | 3.85 | 2026-05-20 | 2026-08-05 | RBA | Asia |
| PLN | 5.75 | 2023-10-04 | 2026-09-03 | NBP | CEEMEA |
| HUF | 6.50 | 2024-09-24 | 2026-08-26 | MNB | CEEMEA |
| CZK | 3.75 | 2026-05-07 | 2026-08-06 | CNB | CEEMEA |
| MXN | 9.00 | 2026-06-26 | 2026-08-14 | Banxico | LatAm |
| BRL | 14.75 | 2026-06-18 | 2026-08-06 | BCB | LatAm |
| COP | 9.50 | 2026-06-30 | 2026-07-31 | BanRep | LatAm |
| CLP | 5.00 | 2026-06-17 | 2026-07-29 | BCCh | LatAm |
| ZAR | 7.50 | 2026-05-29 | 2026-07-17 | SARB | CEEMEA |
| TRY | 42.50 | 2026-06-26 | 2026-07-24 | CBRT | CEEMEA |
| NOK | 4.50 | 2024-12-19 | 2026-08-14 | Norges Bank | Western Europe |
| SEK | 2.25 | 2025-01-29 | 2026-08-20 | Riksbank | Western Europe |
| CNY | 1.40 | 2026-05-20 | — | PBoC (7d reverse repo as anchor) | Asia |
| HKD | 4.75 | 2026-06-18 | — | HKMA (peg — any HKD position is a peg bet per universe.md) | Asia |
| SGD | — | — | — | MAS (FX-centered policy — use SORA for carry) | Asia |
| KRW | 2.75 | 2026-05-29 | 2026-07-10 | BoK | Asia |
| TWD | 2.00 | 2024-03-21 | 2026-09-18 | CBC | Asia |
| INR | 6.00 | 2026-06-06 | 2026-08-08 | RBI | Asia |
| IDR | 5.75 | 2026-05-21 | 2026-08-19 | BI | Asia |

First fill: the inaugural desk run populates every row from the CB sites, with the source page noted in the run record. No dash may remain once an FX position is live in that currency.
