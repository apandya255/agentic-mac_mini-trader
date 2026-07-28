# HEARTBEAT.md

All times America/New_York. Trading days = weekdays excluding US market holidays (check before acting).
Heartbeat ticks are cheap checks only — anything needing research or drafting gets queued for the main brain, not done here.
Delivery: scheduled reports (pre-open, coverage digest, wrap, Saturday run summary, Sunday week-ahead) go to Telegram AND, once connected, the outbound-email mirror. Interrupts, alerts, and real-time book actions are Telegram-only.

## Trading days

- **~21:45 ET, Sun–Thu (once):** Asia open note (T2). Japan/Korea/Australia first session + China/HK open, USDJPY and CNH tone, US futures reaction, anything touching book names or their ADRs. ≤8 lines.
- **~05:30 ET (once):** Morning brief (T2) — the combined London-open + pre-open report, in hand well before the desk. Full Asia session wrap; Europe's first hours — cash, rates first prints, EUR crosses incl. the CEE pairs at their own open; US futures tone; prices.py on book tickers + SPY/RSP/EFA/EEM/USO/GLD overnight; headlines on book names; today's top-3 macro releases from desk/calendar.md. ≤12 lines. (Exempt from quiet hours — mute the device, not the desk.)
- **09:30–16:00 (each tick):** Run prices.py on every open position in desk/positions.md, hedge legs included; update each position's Peak in positions.md — the best LEVEL (ratio/spot/rate/price) in the position's favor — when it makes a new high; the trail anchors to it.
  - **Trail breach** (combined position P&L falls 2–3% from its peak, per AGENTS.md) → paper-execute the cut at the observed price, log level + observed fill, alert Telegram NOW. Fires any hour — FX legs are checked around the clock.
  - **Target touch (+5%)** → do NOT auto-exit. Trigger the PM review per the runner rule: take profit or extend with rationale and re-affirmed flip-condition; the decision and reasoning go to Telegram same tick.
  - Any position within 0.5% of its trail → one warning line. Once per position per day, no repeats.
  - **Hourly, book names only, during their market hours:** headline scan (T1/T2) on open-position names — material news that hasn't yet moved price routes to the owning seat for a same-day flip-condition check; immaterial = silent. *(New — principal to confirm or strike.)*
  - Otherwise silent.
- **~16:30 (once):** Post-close wrap to Telegram: book P&L (paper, carry-adjusted), today's entries/exits with fills, movers, any factor >|0.4|, current leverage stance. ≤12 lines.
- **~17:30 (once):** Daily coverage digest — queue for the main brain (quick-think tier). Macro sweep: all 6 region/commodity mandates, material items only (CB speakers and decisions, releases, politics). Fundamental sweep: only sectors with same-day earnings in universe names — results, guidance, major headlines. Full notes → desk/runs/YYYY-MM-DD.md; digest ≤15 lines → Telegram.

## Weekends

- **Saturday ~10:00 (once):** Queue the weekly desk run for the main brain (mandates → debate → technical → risk → PM per AGENTS.md). Output to desk/runs/, summary + any pitches to Telegram.
- **Sunday ~18:00 (once):** Refresh desk/calendar.md (macro releases, CB meetings, earnings for book + watchlist, holidays) — then send the week-ahead summary. ≤10 lines.

## Always

- **Unscheduled interrupts (any hour, quiet hours included):**
  1. Any position or hedge leg with a daily move ≥2σ (90d trailing σ from prices.py) → fetch headlines on the name, alert with the move and the cause — or "no visible catalyst," which is itself information.
  2. Scheduled CB decision in a book/watchlist currency (dates in desk/rates_table.md) → check outcome vs. consensus within the hour; off-consensus = alert with the surprise quantified.
  3. Critical geopolitical shock with a named transmission channel to the book → alert with the channel stated. No channel, no interrupt — it waits for the digest.
- Empty book → skip position checks; pre-open and wrap still run.
- Quiet hours 22:00–07:00: `HEARTBEAT_OK` only, except trail breaches, the interrupts above, the 21:45 Asia note, and the 05:30 morning brief.
- Data feed down during market hours → one Telegram line, then stay quiet until restored.
- Nothing above triggered → reply `HEARTBEAT_OK` and stop.
