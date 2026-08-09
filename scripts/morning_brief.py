#!/usr/bin/env python3
"""
Morning Brief — fires at 05:30 ET on trading days via launchd.

Generates a 12-line-max pre-open briefing covering:
  - Asia session wrap
  - Europe first hours (cash, rates, EUR crosses)
  - US futures tone
  - Prices on book tickers + SPY/RSP/EFA/EEM/USO/GLD
  - Headlines on book names
  - Top-3 macro releases from desk/calendar.md

Delivered via Telegram and logged to desk/runs/ for email mirror.
Fires during Quiet_Hours (exempt from suppression).

Graceful degradation:
  - Without OPENROUTER_API_KEY, generates a structured data dump
    instead of a prose briefing.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.book_ops import load_book
from src.data_platform.cycle_logger import log_cycle
from src.data_platform.market_calendar import is_trading_day
from src.data_platform.news import NewsScanner
from src.data_platform.prices import PriceService
from src.telegram_bot import send_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("morning_brief")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load secrets from ~/.openclaw/.env per TOOLS.md security model
from src.data_platform.env_loader import load_secrets
load_secrets()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# LLM calls routed through OpenClaw — see src/data_platform/llm.py

# Benchmarks always included in the brief
BENCHMARK_TICKERS = ["SPY", "RSP", "EFA", "EEM", "USO", "GLD"]

# Asia / Europe market proxies for session context
ASIA_TICKERS = ["EWJ", "FXI", "EWY", "EWT", "INDA"]
EUROPE_TICKERS = ["EWG", "EWU", "EWQ", "EWI", "EWP"]

# Desk files
CALENDAR_PATH = PROJECT_ROOT / "desk" / "calendar.md"
RUNS_DIR = PROJECT_ROOT / "desk" / "runs"

# Max lines in the final briefing
MAX_BRIEF_LINES = 12


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------


def get_book_tickers() -> list[str]:
    """Extract active position tickers from book.json."""
    book = load_book()
    positions = book.get("positions", [])
    tickers: list[str] = []

    for pos in positions:
        if pos.get("status") != "active":
            continue
        ticker = pos.get("ticker")
        if ticker:
            tickers.append(ticker)
        hedge = pos.get("hedge_ticker")
        if hedge:
            tickers.append(hedge)

    return list(set(tickers))


def fetch_benchmark_prices(price_service: PriceService) -> dict[str, float | None]:
    """Fetch latest closes for benchmarks + book tickers."""
    book_tickers = get_book_tickers()
    all_tickers = list(set(BENCHMARK_TICKERS + book_tickers))

    prices: dict[str, float | None] = {}
    for ticker in all_tickers:
        prices[ticker] = price_service.get_latest_close(ticker)

    return prices


def fetch_asia_session_data(price_service: PriceService) -> dict[str, float | None]:
    """Fetch latest prices for Asia session proxies."""
    prices: dict[str, float | None] = {}
    for ticker in ASIA_TICKERS:
        prices[ticker] = price_service.get_latest_close(ticker)
    return prices


def fetch_europe_data(price_service: PriceService) -> dict[str, float | None]:
    """Fetch latest prices for European market proxies."""
    prices: dict[str, float | None] = {}
    for ticker in EUROPE_TICKERS:
        prices[ticker] = price_service.get_latest_close(ticker)
    return prices


def fetch_headlines(book_tickers: list[str]) -> list[str]:
    """Fetch top headlines for book tickers via NewsScanner."""
    scanner = NewsScanner()
    headlines: list[str] = []

    for ticker in book_tickers[:5]:  # Limit to avoid excessive API calls
        ticker_headlines = scanner.get_headlines(ticker, max_items=2)
        for h in ticker_headlines:
            if h.relevance in ("high", "medium"):
                headlines.append(f"{ticker}: {h.title}")

    return headlines[:5]  # Cap at 5 headlines


def parse_macro_releases() -> list[str]:
    """Parse top-3 macro releases from desk/calendar.md.

    Looks for the '### Macro releases' subsection under the current week header
    and extracts scheduled release entries (typically formatted as table rows or
    bullet points with time, currency, and release name).
    """
    if not CALENDAR_PATH.exists():
        return []

    content = CALENDAR_PATH.read_text()

    # Look for the "### Macro releases" section header (level 3 heading)
    releases: list[str] = []
    in_macro_section = False

    for line in content.splitlines():
        # Match the actual section header (### Macro releases)
        if re.match(r"^###\s+[Mm]acro\s+[Rr]eleases?", line):
            in_macro_section = True
            continue
        if in_macro_section:
            # Stop at the next section header (## or ###)
            if re.match(r"^#{2,3}\s+", line):
                break
            # Skip empty lines, table separators, and placeholder markers
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("| — |", "| - |", "---", "|---|"):
                continue
            if stripped.startswith("|") and "—" in stripped and len(stripped) < 10:
                continue
            # Clean up markdown table formatting
            clean = stripped.strip("|").strip()
            if clean and clean not in ("—", "-"):
                releases.append(clean)

    return releases[:3]


# ---------------------------------------------------------------------------
# LLM Briefing Generation
# ---------------------------------------------------------------------------


def call_openrouter(prompt: str) -> str | None:
    """Call LLM through OpenClaw gateway to generate the prose briefing."""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from data_platform.llm import call_llm

    system_prompt = (
        "You are a concise macro trading desk briefing writer. "
        "Generate a pre-open morning brief in EXACTLY 12 lines or fewer. "
        "Be factual, use numbers, no fluff. Each line should convey one "
        "distinct piece of information. Format as plain text, no headers."
    )

    result = call_llm(message=prompt, system_prompt=system_prompt, timeout=60)
    if result:
        return result.strip()
    logger.warning("OpenClaw LLM call failed")
    return None


def generate_llm_briefing(data_context: dict) -> str | None:
    """Build the LLM prompt from gathered data and generate the briefing."""
    prompt_parts = []

    # Asia wrap
    asia_prices = data_context.get("asia_prices", {})
    if asia_prices:
        asia_str = ", ".join(
            f"{t}: ${p:.2f}" for t, p in asia_prices.items() if p is not None
        )
        prompt_parts.append(f"Asia session closes: {asia_str}")

    # Europe
    europe_prices = data_context.get("europe_prices", {})
    if europe_prices:
        eu_str = ", ".join(
            f"{t}: ${p:.2f}" for t, p in europe_prices.items() if p is not None
        )
        prompt_parts.append(f"Europe: {eu_str}")

    # US futures / benchmarks
    benchmark_prices = data_context.get("benchmark_prices", {})
    futures_tickers = ["SPY", "RSP", "EFA", "EEM", "USO", "GLD"]
    futures_str = ", ".join(
        f"{t}: ${benchmark_prices[t]:.2f}"
        for t in futures_tickers
        if benchmark_prices.get(t) is not None
    )
    if futures_str:
        prompt_parts.append(f"US benchmarks (last close): {futures_str}")

    # Book positions
    book_tickers = data_context.get("book_tickers", [])
    if book_tickers:
        book_prices_str = ", ".join(
            f"{t}: ${benchmark_prices[t]:.2f}"
            for t in book_tickers
            if benchmark_prices.get(t) is not None
        )
        if book_prices_str:
            prompt_parts.append(f"Book positions: {book_prices_str}")

    # Headlines
    headlines = data_context.get("headlines", [])
    if headlines:
        prompt_parts.append("Headlines: " + "; ".join(headlines[:3]))

    # Macro releases
    macro_releases = data_context.get("macro_releases", [])
    if macro_releases:
        prompt_parts.append("Today's macro: " + "; ".join(macro_releases))
    else:
        prompt_parts.append("Today's macro: No scheduled releases in calendar.")

    prompt = (
        "Generate a 12-line pre-open morning brief from the following data. "
        "Cover: Asia wrap, Europe, US futures tone, book prices, headlines, "
        "and top macro releases.\n\n" + "\n".join(prompt_parts)
    )

    return call_openrouter(prompt)


# ---------------------------------------------------------------------------
# Structured Fallback (no LLM)
# ---------------------------------------------------------------------------


def generate_structured_brief(data_context: dict) -> str:
    """Generate a structured data-dump briefing when no LLM is available."""
    lines: list[str] = []
    today_str = date.today().strftime("%a %b %d")

    lines.append(f"=== MORNING BRIEF — {today_str} (structured, no LLM) ===")

    # Asia wrap
    asia_prices = data_context.get("asia_prices", {})
    asia_available = {t: p for t, p in asia_prices.items() if p is not None}
    if asia_available:
        asia_str = " | ".join(f"{t} ${p:.2f}" for t, p in asia_available.items())
        lines.append(f"Asia: {asia_str}")

    # Europe
    europe_prices = data_context.get("europe_prices", {})
    eu_available = {t: p for t, p in europe_prices.items() if p is not None}
    if eu_available:
        eu_str = " | ".join(f"{t} ${p:.2f}" for t, p in eu_available.items())
        lines.append(f"Europe: {eu_str}")

    # Benchmarks
    benchmark_prices = data_context.get("benchmark_prices", {})
    bench_str = " | ".join(
        f"{t} ${benchmark_prices[t]:.2f}"
        for t in BENCHMARK_TICKERS
        if benchmark_prices.get(t) is not None
    )
    if bench_str:
        lines.append(f"Benchmarks: {bench_str}")

    # Book prices
    book_tickers = data_context.get("book_tickers", [])
    if book_tickers:
        book_str = " | ".join(
            f"{t} ${benchmark_prices[t]:.2f}"
            for t in book_tickers[:6]
            if benchmark_prices.get(t) is not None
        )
        if book_str:
            lines.append(f"Book: {book_str}")

    # Headlines
    headlines = data_context.get("headlines", [])
    if headlines:
        for hl in headlines[:3]:
            lines.append(f"  * {hl}")

    # Macro releases
    macro_releases = data_context.get("macro_releases", [])
    if macro_releases:
        lines.append("Macro today:")
        for rel in macro_releases:
            lines.append(f"  - {rel}")
    else:
        lines.append("Macro: No scheduled releases.")

    # Enforce 12-line max
    return "\n".join(lines[:MAX_BRIEF_LINES])


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def deliver_telegram(briefing: str) -> bool:
    """Send the briefing via Telegram."""
    header = "📋 *Morning Brief*\n\n"
    return send_message(header + briefing)


def log_to_runs(briefing: str) -> Path:
    """Log the briefing to desk/runs/ for email mirror consumption."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    today_str = date.today().strftime("%Y-%m-%d")
    run_file = RUNS_DIR / f"{today_str}_morning_brief.md"

    content = (
        f"# Morning Brief — {today_str}\n\n"
        f"Generated at: {datetime.now().strftime('%H:%M:%S ET')}\n\n"
        f"```\n{briefing}\n```\n"
    )

    # Append if the file already exists (other runs may write to same date)
    if run_file.exists():
        existing = run_file.read_text()
        content = existing + "\n---\n\n" + content

    run_file.write_text(content)
    logger.info(f"Briefing logged to {run_file}")
    return run_file


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Morning brief entry point.

    1. Check is_trading_day() — skip if not
    2. Fetch data: Asia session, Europe, US futures/benchmarks, book prices,
       headlines, macro releases from desk/calendar.md
    3. Generate briefing (LLM prose if OPENROUTER_API_KEY, else structured dump)
    4. Deliver via Telegram + log to desk/runs/ for email mirror
    5. Log cycle
    """
    cycle_start = time.time()

    # Step 1: Check trading day
    if not is_trading_day():
        logger.info("Skipping morning brief — not a trading day.")
        log_cycle(
            cycle_type="morning_brief",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_trading_day"},
            trigger_source="launchd",
        )
        return

    logger.info("Starting morning brief generation.")

    # Step 2: Fetch data
    price_service = PriceService()
    book_tickers = get_book_tickers()

    data_context = {
        "asia_prices": fetch_asia_session_data(price_service),
        "europe_prices": fetch_europe_data(price_service),
        "benchmark_prices": fetch_benchmark_prices(price_service),
        "book_tickers": book_tickers,
        "headlines": fetch_headlines(book_tickers),
        "macro_releases": parse_macro_releases(),
    }

    logger.info(
        f"Data gathered: {len(book_tickers)} book tickers, "
        f"{len(data_context['headlines'])} headlines, "
        f"{len(data_context['macro_releases'])} macro releases."
    )

    # Step 3: Generate briefing
    briefing = None

    if OPENROUTER_API_KEY:
        logger.info("Using LLM (OpenRouter) to generate prose briefing.")
        briefing = generate_llm_briefing(data_context)
        if briefing:
            # Enforce 12-line limit
            brief_lines = briefing.strip().splitlines()
            if len(brief_lines) > MAX_BRIEF_LINES:
                briefing = "\n".join(brief_lines[:MAX_BRIEF_LINES])
    else:
        logger.info("No OPENROUTER_API_KEY — generating structured data dump.")

    if not briefing:
        # Fallback to structured format
        briefing = generate_structured_brief(data_context)

    logger.info(f"Briefing generated ({len(briefing.splitlines())} lines).")

    # Step 4: Deliver
    telegram_success = deliver_telegram(briefing)
    run_path = log_to_runs(briefing)

    # Step 5: Log cycle
    duration = time.time() - cycle_start
    log_cycle(
        cycle_type="morning_brief",
        status="success",
        duration_seconds=duration,
        metrics={
            "lines": len(briefing.splitlines()),
            "book_tickers": len(book_tickers),
            "headlines_found": len(data_context["headlines"]),
            "macro_releases": len(data_context["macro_releases"]),
            "llm_used": bool(OPENROUTER_API_KEY and briefing),
            "telegram_delivered": telegram_success,
            "run_file": str(run_path),
        },
        trigger_source="launchd",
    )

    logger.info(
        f"Morning brief complete in {duration:.1f}s. "
        f"Telegram: {'OK' if telegram_success else 'FAILED'}."
    )


if __name__ == "__main__":
    main()
