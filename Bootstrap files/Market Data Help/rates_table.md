# Policy Rates — desk/rates_table.md

Maintained by the macro seats as a byproduct of the daily sweep; each seat owns its currencies' rows. Feeds: FX carry accrual (carry.py reads this file), CB-decision interrupts (next-meeting dates), and the calendar. A stale row corrupts carry P&L silently — every sweep verifies its rows' "as of" against the CB's own site; any change same-day.

Conventions: rate = the announced policy rate in %, upper bound where a corridor/range is announced (Fed = upper bound of the target range). "Next" = next scheduled decision date (ET date). Rows exist for every currency with an open FX position PLUS the standing set below; a new pair entering the book adds its legs' rows before the fill.

| CCY | Policy rate % | As of (last change) | Next decision | CB | Owner seat |
|-----|---------------|---------------------|---------------|-----|------------|
| USD | — | — | — | Fed | North America |
| EUR | — | — | — | ECB | Western Europe |
| JPY | — | — | — | BoJ | Asia |
| GBP | — | — | — | BoE | Western Europe |
| CHF | — | — | — | SNB | Western Europe |
| CAD | — | — | — | BoC | North America |
| AUD | — | — | — | RBA | Asia |
| PLN | — | — | — | NBP | CEEMEA |
| HUF | — | — | — | MNB | CEEMEA |
| CZK | — | — | — | CNB | CEEMEA |
| MXN | — | — | — | Banxico | LatAm |
| BRL | — | — | — | BCB | LatAm |
| COP | — | — | — | BanRep | LatAm |
| CLP | — | — | — | BCCh | LatAm |
| ZAR | — | — | — | SARB | CEEMEA |
| TRY | — | — | — | CBRT | CEEMEA |
| NOK | — | — | — | Norges Bank | Western Europe |
| SEK | — | — | — | Riksbank | Western Europe |
| CNY | — | — | — | PBoC (7d reverse repo as anchor) | Asia |
| HKD | — | — | — | HKMA (peg — any HKD position is a peg bet per universe.md) | Asia |
| SGD | — | — | — | MAS (FX-centered policy — use SORA for carry) | Asia |
| KRW | — | — | — | BoK | Asia |
| TWD | — | — | — | CBC | Asia |
| INR | — | — | — | RBI | Asia |
| IDR | — | — | — | BI | Asia |

First fill: the inaugural desk run populates every row from the CB sites, with the source page noted in the run record. No dash may remain once an FX position is live in that currency.
