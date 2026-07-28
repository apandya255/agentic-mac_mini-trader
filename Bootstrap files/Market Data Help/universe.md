# Universe — desk/universe.md

## Single names
All current S&P 500 constituents. No fixed list maintained here — verify index membership at pitch time.

## Sector ETFs (cap-weight ↔ equal-weight hedge)
| Sector | ETF | EW Hedge |
|---|---|---|
| Energy | XLE | RSPG |
| Materials | XLB | RSPM |
| Industrials | XLI | RSPN |
| Consumer Discretionary | XLY | RSPD |
| Consumer Staples | XLP | RSPS |
| Health Care | XLV | RSPH |
| Financials | XLF | RSPF |
| Information Technology | XLK | RSPT |
| Communication Services | XLC | RSPC |
| Utilities | XLU | RSPU |
| Real Estate | XLRE | RSPR |

Sector-level ideas hedge against RSP (S&P 500 Equal Weight).

## Country ETFs (20 — confirmed by the principal, 2026-07-27)
**DM (9):** Canada EWC · France EWQ · Germany EWG · Italy EWI · Japan EWJ · Singapore EWS · Spain EWP · UK EWU · US IVV/SPY.
**EM (11):** Brazil EWZ · China MCHI · Hong Kong EWH · India INDA · Indonesia EIDO · Korea EWY · Mexico EWW · Poland EPOL · South Africa EZA · Taiwan EWT · Turkey TUR.
Hedges: DM → EFA or ACWI; EM → EEM or ACWI. **US special case:** EFA excludes North America — a US country view pairs vs. ACWI (or argues ACWX to isolate US-vs-world cleanly). Country trades are now UNBLOCKED; every ticker still passes prices.py --validate before first pitch.
**FX and rates are deliberately BROADER than this list** (principal's instruction): the FX universe is anything passing its two admission gates, the rates universe is every market qualifying under the tiers — this ETF list bounds country-ETF trades only.

## Commodities
| Exposure | Vehicle | Miners/related |
|---|---|---|
| Gold | GLD | GDX |
| Silver | SLV | SIL |
| Copper | CPER | COPX |
| Oil & Gas | USO / XOP | XLE names |

## Macro overlay sleeve (paper — no executability constraint)
Budget: ≤10 of the 30 slots, ≤35% of book risk. Intentional macro positions are sized in factor space; the ±0.6 caps govern the *residual* exposure of the equity book.

**FX — any pair that passes two gates, not a fixed list.** A pair is in scope when (1) its spot quote validates on the feed (staleness + garbage-tick checks per TOOLS.md) and (2) both legs have a policy rate row in desk/rates_table.md for carry accrual. Full G10 set and all G10 crosses; EM vs USD, vs EUR (the natural CEE base — EUR/PLN, EUR/HUF, EUR/CZK), and EM crosses triangulated from validated legs (e.g., MXN/BRL). Carry = policy-rate differential of the two legs, whichever they are. Macro seats propose additions; a pair goes live once prices.py validates it. FX positions are inherently self-hedged — no additional hedge leg; carry accrues daily.
Caveats, encoded not assumed: **NDF currencies** (KRW, TWD, INR, IDR, PHP, MYR) — spot + policy-carry marking is crude vs. forward-implied; allowed, labeled "NDF-proxy marking." **Pegged/managed** (HKD, DKK, Gulf pegs) — a position is a peg bet; requires explicit framing as such or it's rejected. **ARS** — the official/parallel gap makes the public quote near-meaningless for P&L; excluded until the desk defines a defensible mark. **RUB** — excluded.

**Rates — traded in rate space, in every country where a market exists.** A rates position is REC/PAY @ a level, stop/target quoted in rate, DV01 stated. Example: `REC ODF29 @ 14.375 | tgt 13.90 | stop 14.60 | DV01 $X`. Instrument selection follows market structure, in priority order:

1. **Exchange rate futures with public settlements** → trade the contract. US (ZT/ZF/ZN/TN/ZB; full UST curve daily via Treasury.gov par yield CSV), Germany via Eurex (Schatz/Bobl/Bund), UK/Japan/Australia/Canada bond futures, **Brazil DI1** (OD+month+year; exact P&L via PU = 100,000/(1+i)^(du/252)), **Mexico TIIE/F-TIIE** (MexDer; mind the F-TIIE splice).
2. **No futures** → trade the generic government benchmark yield (e.g., REC POLGB 10y @ level), marked off the official daily source: debt agency / central bank / bond market association (ÁKK for HGBs, MinFin/NBP for POLGBs, BanRep/SEN for TES, ChinaBond, FBIL for India, ThaiBMA, KOFIA, etc.).
3. **Short-tenor OIS vs any published overnight index** → settle at maturity against realized compounding. Works in every currency where the CB publishes the O/N fix daily: SOFR, ESTR, SONIA, TONA, CORRA, SARON, F-TIIE, IBR, SELIC, POLONIA... Accrual P&L is exact; intraperiod MTM omitted and labeled. (This is how Colombia IBR OIS runs today, curve-free.)

- IRS/long-tenor swap curves are broker-marked and non-public nearly everywhere — Brazil is the exception because the swap *is* the future. Don't fake swap MTM; use tiers 1–3.
- **Fetchers return the whole curve, never a single point.** Every rates idea is worked per `desk/rates_method.md`: full-strip scan, forwards, carry+roll per tenor, house path vs. market path — then choose outright, steepener/flattener, or fly. Curve trades = one position, one slot, spread-quoted.
- Positions marked off daily official settlements are stop/target-checked once per day at the mark; intraday stop logic applies only to continuously-quoted instruments.
- Per-market conventions, sources, day counts, and fetcher status live in `desk/rates_markets.md` — each macro seat owns its region's rows. Markets go live in the book only after their fetcher validates (feed doctrine). Rollout priority: LatAm + CEE, then DM, then Asia.
- Until a market's fetcher is live, a rates view there may express via FX carry or rate-sensitive ETFs — always labeled as the proxy it is, never presented as the rates trade.

**Credit:** HYG/LQD wrappers only. No public CDX print; the FRED HY OAS series is the monitoring input, not a tradeable.

## Factor definitions (12m beta calc)
Factors are defined at the index/commodity level (Bloomberg convention), computed on the box from the public-feed equivalent:

| Factor | Definition | Box source (yfinance) |
|---|---|---|
| USD | DXY Index | DX-Y.NYB |
| Equities | SPX Index | ^GSPC |
| Rates | USGG10YR | ^TNX (÷10 = yield %) |
| Vol | VIX Index | ^VIX |
| Growth/Value | SGX Index − SVX Index | IVW − IVE (track SGX/SVX exactly; wrapper, same underlying) |
| Crude | CL1 Comdty | CL=F |
| Large/Small | SPX Index − RTY Index | ^GSPC − ^RUT |
| HY credit | CDX HY 5Y | HYG (no public CDX print; optional upgrade: FRED HY OAS, series BAMLH0A0HYM2) |
| Gold | XAU Curncy | GC=F front gold future (≈ spot) |

Rule: commodity factors use the commodity itself (spot/front future), never an ETF wrapper. Validate every box-source ticker in prices.py before first beta run.
