# Requirements — calendar.md Refresh System

## Overview
`desk/calendar.md` is the single source of truth for "what's happening this week." The pre-open brief (05:30 ET), the CB-interrupt system, the coverage sweeps, and the Saturday/Sunday desk runs all read it. Currently the file exists only as an empty template. This spec covers building the refresh script and the scaffolding that keeps it populated.

## Requirements

### 1 — desk/ directory initialisation
**As a** system,  
**I want** the `desk/` directory tree initialised with empty-but-valid placeholder files,  
**so that** all consumers (HEARTBEAT, carry.py, book.py) can assume the path exists and read gracefully.

**Acceptance Criteria:**
- `desk/calendar.md` exists at the workspace root with the four section headers defined in the Bootstrap template.
- `desk/rates_table.md` exists with the 25-row table from Bootstrap, all `—` values intact (populated in the inaugural desk run, not here).
- Both files are committed to git.

---

### 2 — Macro releases section
**As a** T1/T2 consumer of the 05:30 brief,  
**I want** the macro-releases section of `desk/calendar.md` populated for the upcoming 7 days,  
**so that** the morning brief can surface the top-3 releases without re-searching.

**Acceptance Criteria:**
- Each row follows the format: `[Day HH:MM ET] CCY — release (consensus if published) — owning seat`.
- Events covered as a minimum: US NFP (first Friday), US CPI (~13th of month), US PCE, FOMC decisions, ECB decisions, BoJ decisions, BoE decisions, ISM Manufacturing PMI, US Retail Sales. Additional CB decisions pulled from `desk/rates_table.md` Next-decision column where dates fall within the window.
- If a live economic calendar API (e.g., Alpha Vantage) is reachable and within the free-tier budget (≤25 calls/day), it is used as the primary source; the static-rule fallback (day-of-week/day-of-month heuristics from `news.py::upcoming_macro_events()`) fires only when the API call fails.
- Consensus figure is included when returned by the API; omitted (not faked) when unavailable.
- Section is marked with a `_refreshed:` timestamp comment so consumers can detect staleness.

---

### 3 — CB decisions section
**As a** carry.py consumer and CB-interrupt logic,  
**I want** the CB-decisions section of `desk/calendar.md` to mirror the Next-decision column from `desk/rates_table.md`,  
**so that** there is one human-readable view of upcoming CB meetings without the interrupt system needing a second source.

**Acceptance Criteria:**
- Every row in `desk/rates_table.md` with a non-`—` Next-decision date that falls within the next 30 days appears in this section.
- Format: `[Date ET] CCY — CB name — owning seat`.
- If `desk/rates_table.md` is unpopulated (all `—`), the section renders as `| (rates_table.md not yet populated — run inaugural desk run) |` — never silently empty.
- The section is **not** independently sourced; it reads `rates_table.md` only. Duplication is intentional.

---

### 4 — Earnings section
**As a** fundamental-seat consumer,  
**I want** the earnings section of `desk/calendar.md` populated with upcoming earnings for all tickers in the book and watchlist,  
**so that** sweeps and the pre-open brief know which names are reporting this week without a per-ticker fetch.

**Acceptance Criteria:**
- Tickers are sourced from `desk/positions.md` (open positions, all legs) and `desk/universe.md` (watchlist/universe tickers). If either file is absent, the script logs a warning and continues with the other.
- Each row format: `[Date, BMO/AMC] TICKER — owning sector seat`.
- BMO/AMC timing sourced from `yfinance.Ticker.calendar`; when timing is unavailable it is omitted (not guessed).
- Alpha Vantage earnings calendar (`ALPHAVANTAGE_API_KEY` from `~/.openclaw/.env`) is used as a cross-check when a yfinance date is present; discrepancies are flagged in the section as `[DATE CONFLICT: yf=X, av=Y]`.
- Events within the next 14 days are included; beyond 14 days are dropped.
- The existing `NewsScanner.earnings_calendar()` in `src/data_platform/news.py` is used as the yfinance fetch layer — no new yfinance code is written.

---

### 5 — Holidays & early closes section
**As a** HEARTBEAT trading-day check,  
**I want** the US market holidays section of `desk/calendar.md` pre-populated for the full current calendar year,  
**so that** the heartbeat can determine whether today is a trading day without an external fetch.

**Acceptance Criteria:**
- Populated from the NYSE official calendar (fetched once on first Sunday run of the year via `exchange_calendars` library or equivalent; falls back to a hardcoded 2026 list if unavailable).
- Format per entry: `[Date] Holiday name — (early close HH:MM ET)` where applicable.
- The section is static for the year and is only re-fetched on the first Sunday run of a new calendar year (detected by comparing the year in the existing section header against `datetime.today().year`).
- Full closures and early-close days are both included.

---

### 6 — Refresh script (`desk/scripts/calendar_refresh.py`)
**As a** Sunday HEARTBEAT run,  
**I want** a T0 Python script that refreshes all four calendar sections,  
**so that** the agent model tier (T1/T2) does not need to compute or search for calendar data.

**Acceptance Criteria:**
- Script lives at `desk/scripts/calendar_refresh.py` and is listed in `TOOLS.md`'s Script suite.
- Entry point: `python3 desk/scripts/calendar_refresh.py [--dry-run] [--section macro|earnings|cb|holidays|all]`.
- `--dry-run` prints the proposed markdown diff to stdout without writing the file.
- Each section regenerates independently (idempotent: re-running produces the same output if data hasn't changed).
- Script exits non-zero on any data-source failure and prints one error line; it does not retry.
- Total API calls stay within the Alpha Vantage free-tier budget (≤25/day) across all sections; every AV call is logged to stdout with its URL and response HTTP status.
- On success the script writes a final line: `calendar_refresh OK — <timestamp> — <N> events written`.
- The script does **not** send Telegram messages; that is the HEARTBEAT agent's job after calling the script.

---

### 7 — HEARTBEAT integration
**As a** Sunday ~18:00 HEARTBEAT tick,  
**I want** the heartbeat to invoke `calendar_refresh.py` and confirm success before composing the week-ahead summary,  
**so that** the summary always reflects a freshly refreshed calendar.

**Acceptance Criteria:**
- The Sunday heartbeat tick runs `python3 desk/scripts/calendar_refresh.py --section all` as a T0 step before the T2 week-ahead summary.
- If the script exits non-zero, the week-ahead summary notes the failure and uses the previous calendar content rather than fabricating new data.
- The 05:30 brief reads `desk/calendar.md` and surfaces the top-3 macro releases by importance — it does not call the script itself.

---

### 8 — Mid-week update path
**As a** macro seat,  
**I want** to be able to trigger a partial calendar refresh when a CB meeting date changes or a new unscheduled event is confirmed,  
**so that** the calendar is never knowingly stale mid-week.

**Acceptance Criteria:**
- `calendar_refresh.py --section cb` re-reads `desk/rates_table.md` and rewrites only the CB-decisions section.
- `calendar_refresh.py --section macro` re-runs only the macro-releases section.
- The script appends a `_last_updated:` timestamp to the changed section(s) so an agent reading the file can detect that a mid-week refresh occurred.
- Changes are committed to git with a one-line message: `calendar: mid-week update — <section> — <date>`.

---

### 9 — Source and format constraints
- All four sections must parse as valid GitHub Flavored Markdown tables — no plain prose rows.
- The file must never contain fabricated data: every row must trace to a machine-readable source (yfinance, Alpha Vantage, `rates_table.md`, or the exchange calendar library). If a source is unavailable, the row is omitted and a `[SOURCE UNAVAILABLE]` note replaces the section body.
- Secrets (`ALPHAVANTAGE_API_KEY`) are read from `~/.openclaw/.env` via the existing env-loading pattern in the codebase — never hardcoded and never echoed to stdout.
- The script must be compatible with the Python version already in the project's `pyproject.toml` and must not introduce scheduler libraries (APScheduler, Celery, cron wrappers) — scheduling is the HEARTBEAT agent's responsibility.
