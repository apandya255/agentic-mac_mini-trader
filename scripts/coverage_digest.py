#!/usr/bin/env python3
"""
Coverage Digest — runs weekdays at 17:30 ET via launchd.

Generates a daily macro + fundamental coverage sweep using the T2-tier model:
  - Macro sweep across all 6 regions (NA, WEU, Asia, CEEMEA/LatAm, Commodities, Rates)
  - Fundamental sweep for sectors with same-day earnings in universe names
  - Writes full notes to desk/runs/YYYY-MM-DD.md
  - Delivers a 15-line summary via Telegram and email mirror

Graceful degradation: Without OPENROUTER_API_KEY, skips LLM-dependent parts
and logs that the script ran but couldn't generate content.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
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

from src.data_platform.cycle_logger import log_cycle
from src.data_platform.market_calendar import is_trading_day, ET
from src.telegram_bot import send_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("coverage_digest")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load secrets from ~/.openclaw/.env per TOOLS.md security model
from src.data_platform.env_loader import load_secrets
load_secrets()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# T2-tier model for digest generation (cost-effective for sweep work)
T2_MODEL = "anthropic/claude-sonnet-4-20250514"

# Output paths
DESK_RUNS_DIR = PROJECT_ROOT / "desk" / "runs"
CALENDAR_PATH = PROJECT_ROOT / "desk" / "calendar.md"

# ---------------------------------------------------------------------------
# Macro Regions
# ---------------------------------------------------------------------------

MACRO_REGIONS = [
    {
        "id": "macro_northamerica",
        "name": "North America",
        "prompt_focus": (
            "US macro: Fed path, rates, labor, inflation internals, "
            "Treasury supply, consumer. Canada light."
        ),
    },
    {
        "id": "macro_westerneurope",
        "name": "Western Europe",
        "prompt_focus": (
            "ECB policy, EUR rates, UK (BoE, gilt curve), "
            "European growth, PMIs, political risk."
        ),
    },
    {
        "id": "macro_asia",
        "name": "Asia",
        "prompt_focus": (
            "Japan (BoJ, JPY, JGBs), China (PBoC, property, CNH), "
            "Korea, Australia (RBA), India (RBI)."
        ),
    },
    {
        "id": "macro_ceemea_latam",
        "name": "CEEMEA & LatAm",
        "prompt_focus": (
            "EM rates and FX: Turkey, South Africa, Poland, Brazil, Mexico. "
            "CB decisions, political risk, commodity linkages."
        ),
    },
    {
        "id": "macro_commodities",
        "name": "Commodities",
        "prompt_focus": (
            "Crude (WTI/Brent), natural gas, metals (gold, copper), "
            "agricultural. OPEC+, supply disruptions, inventory data."
        ),
    },
    {
        "id": "macro_rates",
        "name": "Global Rates & FX",
        "prompt_focus": (
            "G10 yield curves, cross-market rate differentials, "
            "DXY, major crosses (EUR, JPY, GBP, AUD). "
            "Carry dynamics and positioning."
        ),
    },
]

# ---------------------------------------------------------------------------
# Sector → Earnings Mapping
# ---------------------------------------------------------------------------

# Sectors with their fundamental agent IDs
SECTOR_AGENTS = {
    "energy": "fund_energy",
    "information technology": "fund_infotech",
    "healthcare": "fund_healthcare",
    "financials": "fund_financials",
    "materials": "fund_materials",
    "industrials": "fund_industrials",
    "consumer discretionary": "fund_consdisc",
    "consumer staples": "fund_consstaples",
    "communication services": "fund_commsvcs",
    "utilities": "fund_utilities",
    "real estate": "fund_realestate",
}

# Tickers by sector for earnings matching
SECTOR_TICKERS: dict[str, list[str]] = {
    "energy": [
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "DVN",
    ],
    "information technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ADBE", "ORCL", "AMD", "INTC", "NOW",
    ],
    "healthcare": [
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN", "ISRG",
    ],
    "financials": [
        "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "V", "MA",
    ],
    "materials": [
        "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "CTVA",
    ],
    "industrials": [
        "CAT", "HON", "UNP", "RTX", "GE", "DE", "LMT", "WM", "ETN", "ITW",
    ],
    "consumer discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG",
    ],
    "consumer staples": [
        "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "CL", "KHC",
    ],
    "communication services": [
        "META", "GOOG", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA",
    ],
    "utilities": [
        "NEE", "SO", "DUK", "SRE", "AEP", "D", "XEL", "EXC", "WEC", "ED",
    ],
    "real estate": [
        "PLD", "AMT", "EQIX", "SPG", "O", "PSA", "WELL", "DLR", "AVB", "EXR",
    ],
}


# ---------------------------------------------------------------------------
# LLM Interface
# ---------------------------------------------------------------------------


def _call_llm(system_prompt: str, user_prompt: str) -> str | None:
    """Call OpenRouter LLM with the T2-tier model.

    Returns the response text, or None on failure.
    """
    if not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agentictrading.local",
        "X-Title": "Agentic Trading Coverage Digest",
    }

    payload = json.dumps({
        "model": T2_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
    }).encode("utf-8")

    req = Request(OPENROUTER_API_URL, data=payload, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except (HTTPError, URLError, OSError, KeyError, json.JSONDecodeError) as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Calendar Parsing
# ---------------------------------------------------------------------------


def get_earnings_sectors_today(today: date | None = None) -> list[str]:
    """
    Parse desk/calendar.md to find sectors with same-day earnings.

    Looks for lines matching: [YYYY-MM-DD, BMO/AMC] TICKER — ...
    Returns a list of sector names that have at least one ticker
    reporting earnings today.
    """
    if today is None:
        today = datetime.now(ET).date()

    today_str = today.isoformat()

    sectors_with_earnings: set[str] = set()

    if not CALENDAR_PATH.exists():
        logger.info("desk/calendar.md not found — skipping earnings sector detection.")
        return []

    try:
        calendar_text = CALENDAR_PATH.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"Could not read calendar: {e}")
        return []

    # Match patterns like: [2026-07-28, BMO] AAPL — ...
    # or: [2026-07-28, AMC] MSFT — ...
    pattern = re.compile(
        r"\[" + re.escape(today_str) + r",\s*(BMO|AMC)\]\s+(\w+)"
    )

    for match in pattern.finditer(calendar_text):
        ticker = match.group(2)
        # Find which sector this ticker belongs to
        for sector, tickers in SECTOR_TICKERS.items():
            if ticker in tickers:
                sectors_with_earnings.add(sector)
                break

    if sectors_with_earnings:
        logger.info(
            f"Same-day earnings sectors: {', '.join(sorted(sectors_with_earnings))}"
        )
    else:
        logger.info("No same-day earnings detected from calendar.")

    return sorted(sectors_with_earnings)


# ---------------------------------------------------------------------------
# Macro Sweep
# ---------------------------------------------------------------------------


def run_macro_sweep() -> dict[str, str]:
    """
    Run macro sweep across all 6 regions using the T2-tier model.

    Returns a dict mapping region name → analysis text.
    Empty strings for regions that failed.
    """
    results: dict[str, str] = {}

    system_prompt = (
        "You are a senior macro analyst at a global macro hedge fund. "
        "Provide a concise, material-only summary of today's developments "
        "in your assigned region. Focus on: CB speakers and decisions, "
        "economic releases (actual vs consensus), political risk, "
        "and market-moving events. Skip immaterial noise. "
        "Be specific with numbers and directional language. "
        "Max 10 lines."
    )

    for region in MACRO_REGIONS:
        user_prompt = (
            f"Region: {region['name']}\n"
            f"Focus: {region['prompt_focus']}\n\n"
            f"Summarize today's material macro developments for this region. "
            f"Report only items that matter for positioning or risk. "
            f"If nothing material happened, say so in one line."
        )

        logger.info(f"Running macro sweep: {region['name']}...")
        response = _call_llm(system_prompt, user_prompt)

        if response:
            results[region["name"]] = response.strip()
        else:
            results[region["name"]] = "(No data — LLM call failed or unavailable)"

    return results


# ---------------------------------------------------------------------------
# Fundamental Sweep
# ---------------------------------------------------------------------------


def run_fundamental_sweep(sectors: list[str]) -> dict[str, str]:
    """
    Run fundamental sweep for sectors with same-day earnings.

    Args:
        sectors: List of sector names to sweep.

    Returns a dict mapping sector name → analysis text.
    """
    if not sectors:
        return {}

    results: dict[str, str] = {}

    system_prompt = (
        "You are a senior sector analyst at an elite fundamental equity fund. "
        "Summarize today's earnings results, guidance, and major headlines "
        "for your assigned sector. Focus on: EPS vs consensus, revenue beat/miss, "
        "guidance revisions, and any thesis-changing developments. "
        "Be specific with numbers. Max 8 lines per company reporting."
    )

    for sector in sectors:
        tickers = SECTOR_TICKERS.get(sector, [])
        user_prompt = (
            f"Sector: {sector.title()}\n"
            f"Universe tickers: {', '.join(tickers)}\n\n"
            f"Summarize today's earnings results and material headlines "
            f"for any tickers in this sector that reported today. "
            f"Include: EPS vs consensus, revenue, guidance, and market reaction. "
            f"If no earnings reported, note any material sector headlines."
        )

        logger.info(f"Running fundamental sweep: {sector}...")
        response = _call_llm(system_prompt, user_prompt)

        if response:
            results[sector] = response.strip()
        else:
            results[sector] = "(No data — LLM call failed or unavailable)"

    return results


# ---------------------------------------------------------------------------
# Output Writing
# ---------------------------------------------------------------------------


def write_full_notes(
    today: date,
    macro_results: dict[str, str],
    fundamental_results: dict[str, str],
) -> Path:
    """
    Write full coverage digest notes to desk/runs/YYYY-MM-DD.md.

    Returns the path to the written file.
    """
    DESK_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DESK_RUNS_DIR / f"{today.isoformat()}.md"

    lines = [
        f"# Coverage Digest — {today.isoformat()}",
        "",
        f"Generated at {datetime.now(ET).strftime('%H:%M ET')} by coverage_digest.py",
        "",
        "---",
        "",
        "## Macro Sweep",
        "",
    ]

    for region_name, analysis in macro_results.items():
        lines.append(f"### {region_name}")
        lines.append("")
        lines.append(analysis)
        lines.append("")

    if fundamental_results:
        lines.append("---")
        lines.append("")
        lines.append("## Fundamental Sweep (Same-Day Earnings)")
        lines.append("")

        for sector_name, analysis in fundamental_results.items():
            lines.append(f"### {sector_name.title()}")
            lines.append("")
            lines.append(analysis)
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Full notes written to: {output_path}")
    return output_path


def generate_summary(
    macro_results: dict[str, str],
    fundamental_results: dict[str, str],
    today: date,
) -> str:
    """
    Generate a 15-line summary of the coverage digest.

    Uses LLM if available; falls back to a template-based summary.
    """
    # Try LLM-generated summary
    if OPENROUTER_API_KEY:
        # Compile the full notes for summarization
        full_content = []
        for region, text in macro_results.items():
            full_content.append(f"[{region}] {text}")
        for sector, text in fundamental_results.items():
            full_content.append(f"[Earnings: {sector}] {text}")

        combined = "\n\n".join(full_content)

        system_prompt = (
            "You are a senior portfolio manager's assistant. "
            "Condense the following coverage digest into exactly 15 lines. "
            "Each line should be a self-contained bullet capturing one material item. "
            "Prioritize: CB decisions > economic releases > earnings > political risk. "
            "Use terse desk language. Include specific numbers. "
            "Format: each line starts with a dash and the region/sector tag."
        )

        user_prompt = (
            f"Coverage Digest for {today.isoformat()}:\n\n"
            f"{combined}\n\n"
            f"Produce exactly 15 lines summarizing the material items above."
        )

        response = _call_llm(system_prompt, user_prompt)
        if response:
            # Ensure we don't exceed 15 lines
            summary_lines = response.strip().splitlines()[:15]
            return "\n".join(summary_lines)

    # Template-based fallback if LLM unavailable
    summary_lines = [f"Coverage Digest — {today.isoformat()}"]

    # Add macro headlines (up to 2 lines per region, max 12 total)
    macro_line_count = 0
    for region, text in macro_results.items():
        if macro_line_count >= 12:
            break
        first_line = text.split("\n")[0][:120] if text else "No material updates"
        summary_lines.append(f"- [{region}] {first_line}")
        macro_line_count += 1

    # Add earnings headlines (remaining lines)
    for sector, text in fundamental_results.items():
        if len(summary_lines) >= 15:
            break
        first_line = text.split("\n")[0][:120] if text else "No reports"
        summary_lines.append(f"- [Earnings: {sector.title()}] {first_line}")

    # Pad to 15 lines if needed
    while len(summary_lines) < 15:
        summary_lines.append(f"- [Digest] End of coverage for {today.isoformat()}")
        break  # Don't over-pad, just add a closing line

    return "\n".join(summary_lines[:15])


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def deliver_summary(summary: str, today: date) -> None:
    """
    Deliver the 15-line summary via Telegram and log for email mirror.

    The email mirror is handled by the Telegram bot's logging which
    the email system picks up. In production, the outbound email
    integration reads from the delivery logs.
    """
    header = f"*Coverage Digest — {today.isoformat()}*\n\n"
    full_message = header + summary

    try:
        success = send_message(full_message)
        if success:
            logger.info("Summary delivered via Telegram.")
        else:
            logger.warning("Telegram delivery failed after retry.")
    except Exception as e:
        logger.error(f"Telegram delivery error: {e}")

    # Log the summary for email mirror pickup
    email_log_dir = PROJECT_ROOT / "memos" / "logs"
    email_log_dir.mkdir(parents=True, exist_ok=True)
    email_log_path = email_log_dir / f"email_mirror_digest_{today.isoformat()}.txt"
    try:
        email_log_path.write_text(full_message, encoding="utf-8")
        logger.info(f"Email mirror log written: {email_log_path}")
    except OSError as e:
        logger.warning(f"Could not write email mirror log: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Coverage digest entry point.

    1. Check is_trading_day() — skip if not
    2. Determine sectors with same-day earnings from desk/calendar.md
    3. Run macro sweep across 6 regions
    4. Run fundamental sweep for earnings sectors
    5. Write full notes to desk/runs/YYYY-MM-DD.md
    6. Generate 15-line summary
    7. Deliver via Telegram + log for email mirror
    8. Log cycle
    """
    cycle_start = time.time()
    today = datetime.now(ET).date()

    # Step 1: Trading day check
    if not is_trading_day(today):
        logger.info("Skipping coverage digest — not a trading day.")
        log_cycle(
            cycle_type="coverage_digest",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_trading_day"},
            trigger_source="launchd",
        )
        return

    logger.info(f"Starting coverage digest for {today.isoformat()}")

    # Graceful degradation check
    if not OPENROUTER_API_KEY:
        logger.warning(
            "OPENROUTER_API_KEY not set — cannot generate LLM content. "
            "Logging run and exiting."
        )
        log_cycle(
            cycle_type="coverage_digest",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "no_api_key"},
            trigger_source="launchd",
        )
        return

    # Step 2: Determine same-day earnings sectors
    earnings_sectors = get_earnings_sectors_today(today)

    # Step 3: Macro sweep (6 regions)
    logger.info("Running macro sweep across 6 regions...")
    macro_results = run_macro_sweep()
    macro_success_count = sum(
        1 for v in macro_results.values()
        if not v.startswith("(No data")
    )
    logger.info(
        f"Macro sweep complete: {macro_success_count}/{len(MACRO_REGIONS)} regions."
    )

    # Step 4: Fundamental sweep for earnings sectors
    fundamental_results: dict[str, str] = {}
    if earnings_sectors:
        logger.info(
            f"Running fundamental sweep for {len(earnings_sectors)} sectors..."
        )
        fundamental_results = run_fundamental_sweep(earnings_sectors)
        fund_success_count = sum(
            1 for v in fundamental_results.values()
            if not v.startswith("(No data")
        )
        logger.info(
            f"Fundamental sweep complete: "
            f"{fund_success_count}/{len(earnings_sectors)} sectors."
        )
    else:
        logger.info("No earnings sectors today — skipping fundamental sweep.")

    # Step 5: Write full notes
    notes_path = write_full_notes(today, macro_results, fundamental_results)

    # Step 6: Generate 15-line summary
    logger.info("Generating 15-line summary...")
    summary = generate_summary(macro_results, fundamental_results, today)
    logger.info("Summary generated.")

    # Step 7: Deliver via Telegram + email mirror
    deliver_summary(summary, today)

    # Step 8: Log cycle
    duration = time.time() - cycle_start
    log_cycle(
        cycle_type="coverage_digest",
        status="success",
        duration_seconds=duration,
        metrics={
            "macro_regions_covered": macro_success_count,
            "earnings_sectors_covered": len(earnings_sectors),
            "fundamental_sectors_with_data": len(fundamental_results),
            "notes_path": str(notes_path),
        },
        trigger_source="launchd",
    )

    logger.info(
        f"Coverage digest complete in {duration:.1f}s. "
        f"Notes: {notes_path}"
    )


if __name__ == "__main__":
    main()
