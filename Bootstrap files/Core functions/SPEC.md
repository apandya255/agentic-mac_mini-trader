# T0 Build Spec — desk/scripts/ (v1)
Three scripts, built and validated in this order. Conventions for all: Python 3.11+, yfinance + pandas only; deterministic; every output line carries the source's own timestamp; exit codes 0=ok, 2=stale/garbage, 3=fetch failure; one retry then fail loudly; no secrets touched; TSV default, `--json` optional. A script emits numbers or an error — never a guess.

## 1. prices.py — build first, validate before anything else runs
`python3 prices.py TICKER [TICKER ...] [--json] [--validate]`

Per ticker: `ticker | last | feed_ts (ET) | prior_close | pct_chg | sigma90d | flags`
- **sigma90d:** trailing 90-day close-to-close daily σ (%). Feeds the 2σ interrupt: |pct_chg| ≥ 2·sigma90d → flag `2SIGMA`.
- **Instrument classes & market hours** (drives staleness): equities/ETFs 09:30–16:00 ET Mon–Fri; FX Sun 17:00–Fri 17:00 ET; futures (=F) per session, approximate as 18:00–17:00 ET Sun–Fri; indices (^) as equities. Staleness: quote older than 4h *while that market is open* → flag `STALE`, exit 2.
- **Garbage guard:** single-tick move >3% with prior tick <1h old → re-fetch once; persists → flag `GARBAGE`, exit 2. Never let a flagged quote mark anything.
- **Second source:** if ALPHAVANTAGE_API_KEY is set, a yfinance fetch failure or GARBAGE flag triggers one Alpha Vantage retry (flagged `SRC=AV` in output, call logged against the daily budget). AV is never polled in routine ticks on a free key.
- **--validate:** 90d history pull — gaps, NaNs, zero-volume days, split/dividend sanity. A ticker enters the tradeable universe only after `--validate` passes clean (feed doctrine). Store pass date in desk/universe.md.
- Quirks to encode: ^TNX = 10y yield ×10 (divide by 10); ^IRX is 13-week; FX pairs quote-convention noted in output (EURPLN=X = PLN per EUR).

## 2. carry.py
`python3 carry.py [--accrue]`
- Parses desk/rates_table.md (currency | policy rate | last change | next meeting). Malformed row = exit 3 with the row named.
- For each open FX position (from positions.md): daily accrual = (r_long_ccy − r_short_ccy)/365 × notional, sign per position direction. `--accrue` appends today's row to desk/carry_ledger.csv (date, pair, rate_diff, accrual, cumulative); idempotent per date — run twice, write once.
- Output: per-pair carry summary book.py consumes.

## 3. book.py — the numbers the wrap narrates
`python3 book.py [--json]`
- Parses desk/positions.md, calls prices.py on every leg, folds in carry.py cumulative accruals.
- **Per position:** positions are one-line level instruments per positions.md — pairs compute as the ratio (1:1 default; apply Wts when beta-adjusted), FX as carry-adjusted spot, rates per their tier convention, outrights as price. Marks per leg feed the level; P&L ($ and % of book) net of stored fill (fills are recorded already slippage-adjusted at entry — book.py never re-haircuts), distance to stop/target, `STOP`/`TARGET`/`2SIGMA` flags, days held.
- **Book level:** cash balance accrues daily at SOFR (NY Fed fixing via FRED series SOFR; idempotent per date, same pattern as carry.py) and folds into total return; gross, net, position count vs 30-cap, leverage; **factor betas:** per instrument, 12m daily-return regression vs each factor series (mappings in universe.md), cached in desk/scripts/.beta_cache.json and refreshed if older than 5 trading days; book beta = Σ(weight × instrument beta) per factor; flag any |beta| > 0.4 (early warning) and > 0.6 (breach).
- **v1 scope:** book.py prices legs via prices.py only. Positions marked off daily official curves (tier-2/3 rates) are out of scope until curves.py (v1.2) — if one appears in positions.md before then, report it as "unpriceable at v1" and exit 2 rather than improvising a mark.
- Any `STALE`/`GARBAGE` leg → that position reports NO P&L (marked "unpriced") and book.py exits 2; a wrap built on a flagged book says so instead of printing fiction.

## Acceptance tests (shakedown week — all must pass before first tick)
1. prices.py: AAPL, SPY, EURPLN=X, GC=F, ^TNX — cross-check last/prior/σ against Alpha Vantage (independent source, automated); ^TNX ÷10 correct.
2. Weekend behavior: Saturday run on SPY → no STALE (market closed); on EURUSD=X mid-Saturday → STALE fires correctly.
3. σ math: recompute one ticker's 90d σ by hand in pandas; match to 4 decimals.
4. carry.py: seed rates_table with two currencies, fake 1M position, verify daily accrual sign and magnitude by hand; run --accrue twice, one ledger row.
5. book.py: two fake positions (one equity pair, one FX), force a stop-flag by editing the stop level; verify flags, P&L arithmetic, beta cache creation, and exit-2 behavior on a garbage-injected quote.
6. Treasury cross-check: ^TNX (÷10) vs Treasury.gov par 10y same day, within a few bps.
