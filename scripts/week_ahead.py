#!/usr/bin/env python3
"""
Sunday Week-Ahead — fires at 18:00 ET every Sunday via launchd.

Refreshes desk/calendar.md with the coming week's:
  - Macro releases (by region, with consensus where available)
  - Central bank decisions (from desk/rates_table.md + search)
  - Earnings for book + watchlist names
  - US market holidays / early closes

Delivers a 10-line-max week-ahead summary via Telegram.

Graceful degradation:
  - Without OPENROUTER_API_KEY, generates a placeholder noting that
    the calendar refresh could not run without LLM access.
  - Without BRAVE_API_KEY, LLM generates from training knowledge only.

Requirements: 12.1, 12.2
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.cycle_logger import log_cycle
from src.telegram_bot import send_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("week_ahead")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load secrets from ~/.openclaw/.env per TOOLS.md security model
from src.data_platform.env_loader import load_secrets
load_secrets()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# Model for week-ahead generation
LLM_MODEL = "anthropic/claude-sonnet-4-20250514"

# Paths
CALENDAR_PATH = PROJECT_ROOT / "desk" / "calendar.md"
RATES_TABLE_PATH = PROJECT_ROOT / "desk" / "rates_table.md"
BOOK_PATH = PROJECT_ROOT / "memos" / "state" / "book.json"

# ---------------------------------------------------------------------------
# US Market Holidays (static, Requirement 16.3)
# ---------------------------------------------------------------------------

US_MARKET_HOLIDAYS_2025 = [
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
]

US_MARKET_HOLIDAYS_2026 = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
]

ALL_HOLIDAYS = US_MARKET_HOLIDAYS_2025 + US_MARKET_HOLIDAYS_2026


# ---------------------------------------------------------------------------
# Day-of-Week Check
# ---------------------------------------------------------------------------


def is_sunday() -> bool:
    """Check if today is Sunday in ET."""
    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)
    except ImportError:
        now_et = datetime.now()

    return now_et.weekday() == 6  # Sunday


# ---------------------------------------------------------------------------
# Context Gathering
# ---------------------------------------------------------------------------


def get_week_dates(today: date | None = None) -> tuple[date, date]:
    """
    Return (monday, friday) for the upcoming week.

    If called on Sunday, returns the dates for the following Mon-Fri.
    """
    if today is None:
        try:
            import pytz
            et = pytz.timezone("US/Eastern")
            today = datetime.now(et).date()
        except ImportError:
            today = date.today()

    # Move to next Monday
    days_ahead = 7 - today.weekday()  # Sunday weekday=6, so 7-6=1
    if today.weekday() != 6:
        # If not Sunday, go to next Monday
        days_ahead = (7 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
    monday = today + timedelta(days=days_ahead)
    friday = monday + timedelta(days=4)
    return monday, friday


def get_holidays_for_week(monday: date, friday: date) -> list[str]:
    """
    Return any US market holidays that fall within monday-friday.
    """
    holidays_in_week = []
    current = monday
    while current <= friday:
        if current.isoformat() in ALL_HOLIDAYS:
            holidays_in_week.append(current.isoformat())
        current += timedelta(days=1)
    return holidays_in_week


def read_rates_table() -> str:
    """
    Read desk/rates_table.md for upcoming CB decisions.

    Returns the raw text (to pass to LLM for extraction), or empty string.
    """
    if not RATES_TABLE_PATH.exists():
        return ""
    try:
        return RATES_TABLE_PATH.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"Could not read rates_table.md: {e}")
        return ""


def get_book_tickers() -> list[str]:
    """
    Read book.json and return tickers of active positions.
    """
    if not BOOK_PATH.exists():
        return []
    try:
        with open(BOOK_PATH, "r", encoding="utf-8") as f:
            book = json.load(f)
        positions = book.get("positions", [])
        tickers = []
        for pos in positions:
            if pos.get("status") == "active":
                ticker = pos.get("ticker", "")
                if ticker:
                    tickers.append(ticker)
                # Also grab hedge ticker if present
                hedge_ticker = pos.get("hedge_ticker", "")
                if hedge_ticker:
                    tickers.append(hedge_ticker)
        return tickers
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not read book.json: {e}")
        return []


# ---------------------------------------------------------------------------
# Brave Search (Optional)
# ---------------------------------------------------------------------------


def brave_search(query: str) -> str | None:
    """
    Execute a Brave search and return snippet text.

    Returns concatenated snippets, or None if unavailable.
    """
    if not BRAVE_API_KEY:
        return None

    url = f"https://api.search.brave.com/res/v1/web/search?q={query}&count=5"
    req = Request(url, method="GET")
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "gzip")
    req.add_header("X-Subscription-Token", BRAVE_API_KEY)

    try:
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = data.get("web", {}).get("results", [])
            snippets = [r.get("description", "") for r in results[:5]]
            return "\n".join(snippets) if snippets else None
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"Brave search failed for '{query}': {e}")
        return None


# ---------------------------------------------------------------------------
# LLM Interface
# ---------------------------------------------------------------------------


def _call_llm(system_prompt: str, user_prompt: str) -> str | None:
    """
    Call OpenRouter LLM.

    Returns the response text, or None on failure.
    """
    if not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agentictrading.local",
        "X-Title": "Agentic Trading Week Ahead",
    }

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 3000,
        "temperature": 0.3,
    }).encode("utf-8")

    req = Request(OPENROUTER_API_URL, data=payload, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except (HTTPError, URLError, OSError, KeyError, json.JSONDecodeError) as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Calendar Refresh
# ---------------------------------------------------------------------------


def refresh_calendar(monday: date, friday: date) -> str | None:
    """
    Use LLM (+ optional Brave search context) to generate the weekly calendar.

    Returns the calendar markdown content, or None if LLM is unavailable.
    """
    # Gather context
    rates_table = read_rates_table()
    book_tickers = get_book_tickers()
    holidays = get_holidays_for_week(monday, friday)

    # Optionally search for upcoming macro releases
    search_context = ""
    if BRAVE_API_KEY:
        week_str = f"{monday.isoformat()} to {friday.isoformat()}"
        macro_search = brave_search(
            f"US economic calendar week {week_str} macro releases"
        )
        if macro_search:
            search_context += f"\nBrave search — macro releases:\n{macro_search}\n"

        cb_search = brave_search(
            f"central bank decisions {week_str} Fed ECB BoJ BoE"
        )
        if cb_search:
            search_context += f"\nBrave search — CB decisions:\n{cb_search}\n"

        if book_tickers:
            earnings_search = brave_search(
                f"earnings calendar {week_str} {' '.join(book_tickers[:10])}"
            )
            if earnings_search:
                search_context += (
                    f"\nBrave search — earnings:\n{earnings_search}\n"
                )

    # Build LLM prompt
    system_prompt = (
        "You are a senior macro strategist populating a trading desk calendar "
        "for the upcoming week. You must produce a well-structured markdown "
        "document with four sections: Macro releases, CB decisions, Earnings, "
        "and Holidays. Use the specific format described below. "
        "Be concise, factual, and use official scheduling where known. "
        "If you don't have confirmed data for a section, write '| — |' "
        "as a placeholder."
    )

    holidays_str = ", ".join(holidays) if holidays else "None"
    tickers_str = ", ".join(book_tickers) if book_tickers else "No active positions"

    user_prompt = f"""Generate the desk/calendar.md content for the week of {monday.isoformat()} to {friday.isoformat()}.

Context:
- Rates table (CB next decisions): {rates_table[:2000] if rates_table else 'Not available'}
- Book tickers to track earnings for: {tickers_str}
- Known holidays this week: {holidays_str}
{search_context}

Required format:

## Week of {monday.isoformat()}

### Macro releases
Format each entry as: [Day HH:MM ET] CCY — release (consensus if published) — owning seat
Include: US (NFP, CPI, PPI, retail, PMI, Fed speakers), EUR (ECB speakers, PMIs), GBP (BoE, PMIs), JPY (BoJ), AUD (RBA), CAD (BoC), CNY (PBoC)

### CB decisions
Format: [Date] Central Bank — current rate — consensus/expected action
Include any CB decisions scheduled this week from the rates table.

### Earnings — book & watchlist
Format: [Date, BMO/AMC] TICKER — owning sector seat
Include earnings for the book tickers listed above and major S&P 500 names reporting this week.

### Holidays & early closes
List any US market holidays or early closes this week.
If none, write: No US market holidays this week.

Output ONLY the markdown calendar content starting with '## Week of'. No preamble."""

    return _call_llm(system_prompt, user_prompt)


def write_calendar(calendar_content: str, monday: date) -> None:
    """
    Write/refresh desk/calendar.md with the new week's content.

    Preserves the file header and replaces the week section.
    """
    header = (
        "# Calendar — desk/calendar.md\n\n"
        "The single source for \"what's happening\" — the 05:30 brief, sweeps, "
        "and session notes read THIS file instead of re-searching. Refreshed "
        "every Sunday in the week-ahead run (HEARTBEAT.md); mid-week additions "
        "allowed when a seat learns of a new event (unscheduled CB meeting, "
        "moved earnings date) — dated, sourced, never silently.\n\n"
        "Sections and sources:\n"
        "- **Macro releases (week ahead):** from the stats-agency and CB "
        "schedules each macro seat monitors. Format: `[Day HH:MM ET] CCY — "
        "release (consensus if published) — owning seat`.\n"
        "- **CB decisions:** mirrors rates_table.md Next-decision column — "
        "the interrupt system reads rates_table as truth; this section is the "
        "human-readable view.\n"
        "- **Earnings (book + watchlist names):** yfinance earnings dates, "
        "batch-refreshed Sundays; Alpha Vantage earnings calendar as "
        "cross-source. Format: `[Date, BMO/AMC] TICKER — owning sector seat`.\n"
        "- **US market holidays (static, verify annually):** the year's NYSE "
        "full closures and early closes — populated at first Sunday refresh "
        "from the exchange's official calendar; HEARTBEAT trading-day checks "
        "read this list.\n\n"
    )

    full_content = header + calendar_content + "\n"

    try:
        CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALENDAR_PATH.write_text(full_content, encoding="utf-8")
        logger.info(f"Calendar refreshed: {CALENDAR_PATH}")
    except OSError as e:
        logger.error(f"Failed to write calendar: {e}")
        raise


# ---------------------------------------------------------------------------
# Summary Generation
# ---------------------------------------------------------------------------


def generate_summary(calendar_content: str, monday: date, friday: date) -> str:
    """
    Generate a 10-line week-ahead summary.

    Uses LLM if available; falls back to a template extraction.
    """
    if OPENROUTER_API_KEY:
        system_prompt = (
            "You are a senior portfolio manager's assistant. "
            "Condense the following weekly calendar into exactly 10 lines. "
            "Each line should be a self-contained bullet capturing one key event. "
            "Prioritize: CB decisions > major macro releases (NFP, CPI) > "
            "large-cap earnings > holidays. "
            "Use terse desk language. Include specific dates and times. "
            "Format: each line starts with a dash."
        )

        user_prompt = (
            f"Week-Ahead Calendar ({monday.isoformat()} to {friday.isoformat()}):\n\n"
            f"{calendar_content}\n\n"
            f"Produce exactly 10 lines summarizing the most important events."
        )

        response = _call_llm(system_prompt, user_prompt)
        if response:
            lines = response.strip().splitlines()[:10]
            return "\n".join(lines)

    # Template fallback
    lines = [
        f"Week Ahead: {monday.isoformat()} to {friday.isoformat()}",
    ]

    # Extract key items from calendar content
    cal_lines = calendar_content.splitlines()
    event_lines = [
        ln.strip() for ln in cal_lines
        if ln.strip() and not ln.startswith("#") and ln.strip() != "| — |"
    ]

    for evt in event_lines[:9]:
        lines.append(f"- {evt[:120]}")

    # Pad if needed
    while len(lines) < 10:
        lines.append(f"- [Week-Ahead] See desk/calendar.md for full schedule")
        break

    return "\n".join(lines[:10])


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def deliver_summary(summary: str, monday: date) -> bool:
    """
    Deliver the 10-line week-ahead summary via Telegram.

    Returns True if delivery succeeded.
    """
    header = f"*Week Ahead — {monday.isoformat()}*\n\n"
    full_message = header + summary

    try:
        success = send_message(full_message)
        if success:
            logger.info("Week-ahead summary delivered via Telegram.")
        else:
            logger.warning("Telegram delivery failed after retry.")
        return success
    except Exception as e:
        logger.error(f"Telegram delivery error: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Week-ahead entry point.

    1. Check it's Sunday (skip otherwise)
    2. Determine upcoming week dates
    3. Use LLM (or Brave search + template) to gather macro releases,
       CB meetings, earnings, and holidays
    4. Write/refresh desk/calendar.md with the gathered data
    5. Generate a 10-line summary of key events
    6. Deliver via Telegram
    7. Log cycle
    """
    cycle_start = time.time()

    # Step 1: Sunday check
    if not is_sunday():
        logger.info("Skipping week-ahead — not Sunday.")
        log_cycle(
            cycle_type="week_ahead",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_sunday"},
            trigger_source="launchd",
        )
        return

    logger.info("Starting Sunday week-ahead calendar refresh...")

    # Step 2: Determine week dates
    monday, friday = get_week_dates()
    logger.info(f"Generating calendar for week of {monday.isoformat()} to {friday.isoformat()}")

    # Graceful degradation: Without OPENROUTER_API_KEY, generate placeholder
    if not OPENROUTER_API_KEY:
        logger.warning(
            "OPENROUTER_API_KEY not set — cannot generate calendar content. "
            "Writing placeholder and notifying via Telegram."
        )

        # Write placeholder calendar
        placeholder_content = (
            f"## Week of {monday.isoformat()}\n\n"
            f"### Macro releases\n"
            f"| — | (Calendar refresh could not run without LLM access)\n\n"
            f"### CB decisions\n"
            f"| — | (Calendar refresh could not run without LLM access)\n\n"
            f"### Earnings — book & watchlist\n"
            f"| — | (Calendar refresh could not run without LLM access)\n\n"
            f"### Holidays & early closes\n"
        )

        # Still add known holidays from static list
        holidays = get_holidays_for_week(monday, friday)
        if holidays:
            for h in holidays:
                placeholder_content += f"- {h} — US market holiday\n"
        else:
            placeholder_content += "No US market holidays this week.\n"

        write_calendar(placeholder_content, monday)

        # Send Telegram notification about degraded state
        placeholder_summary = (
            f"Week-ahead calendar refresh ({monday.isoformat()}) ran without "
            f"LLM access. desk/calendar.md updated with placeholder. "
            f"Manual review recommended."
        )
        send_message(placeholder_summary)

        log_cycle(
            cycle_type="week_ahead",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "no_api_key", "week_start": monday.isoformat()},
            trigger_source="launchd",
        )
        return

    # Step 3: Refresh calendar via LLM (+ Brave search if available)
    logger.info("Calling LLM to generate calendar content...")
    calendar_content = refresh_calendar(monday, friday)

    if not calendar_content:
        logger.error("Failed to generate calendar content from LLM.")
        log_cycle(
            cycle_type="week_ahead",
            status="failure",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "llm_failed", "week_start": monday.isoformat()},
            error="LLM call returned no content",
            trigger_source="launchd",
        )
        return

    # Step 4: Write/refresh desk/calendar.md
    logger.info("Writing calendar to desk/calendar.md...")
    write_calendar(calendar_content, monday)

    # Step 5: Generate 10-line summary
    logger.info("Generating 10-line week-ahead summary...")
    summary = generate_summary(calendar_content, monday, friday)
    logger.info("Summary generated.")

    # Step 6: Deliver via Telegram
    delivery_success = deliver_summary(summary, monday)

    # Step 7: Log cycle
    duration = time.time() - cycle_start
    log_cycle(
        cycle_type="week_ahead",
        status="success" if delivery_success else "failure",
        duration_seconds=duration,
        metrics={
            "week_start": monday.isoformat(),
            "week_end": friday.isoformat(),
            "calendar_lines": len(calendar_content.splitlines()),
            "summary_lines": len(summary.strip().splitlines()),
            "brave_available": bool(BRAVE_API_KEY),
            "delivery_success": delivery_success,
        },
        error="Telegram delivery failed" if not delivery_success else None,
        trigger_source="launchd",
    )

    logger.info(
        f"Week-ahead complete in {duration:.1f}s. "
        f"Calendar: {CALENDAR_PATH}"
    )


if __name__ == "__main__":
    main()
