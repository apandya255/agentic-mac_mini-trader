#!/usr/bin/env python3
"""
Asia Open Note — fires at 21:45 ET Sunday through Thursday via launchd.

Generates an 8-line-max Asia session preview covering:
  - Japan/Korea/Australia first session
  - China/HK open
  - USDJPY and CNH tone
  - US futures reaction
  - Anything touching book names or their ADRs

Delivers via Telegram. Fires during Quiet_Hours (exempt from suppression).

Graceful degradation:
  - If OPENROUTER_API_KEY is set, uses LLM to generate a concise 8-line summary.
  - If not set, generates a data-only template message from fetched prices.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.book_ops import load_book
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
logger = logging.getLogger("asia_note")

# ---------------------------------------------------------------------------
# Asia Market Tickers (yfinance symbols)
# ---------------------------------------------------------------------------

# Nikkei 225 futures / ETF proxy
ASIA_TICKERS = {
    "nikkei": "^N225",       # Nikkei 225 index
    "kospi": "^KS11",        # KOSPI composite
    "asx": "^AXJO",          # ASX 200
    "hsi": "^HSI",           # Hang Seng Index
    "usdjpy": "JPY=X",       # USD/JPY
    "usdcnh": "CNH=X",       # USD/CNH (offshore yuan)
    "es_futures": "ES=F",    # S&P 500 E-mini futures
}

# Known ADR mappings — tickers with significant Asia exposure
# Maps US tickers to their Asian market connection
ADR_EXPOSURE: dict[str, str] = {
    # Japanese ADRs
    "TM": "Japan (Toyota)",
    "SONY": "Japan (Sony)",
    "MUFG": "Japan (Mitsubishi UFJ)",
    "NMR": "Japan (Nomura)",
    "HMC": "Japan (Honda)",
    # Korean ADRs
    "005930.KS": "Korea (Samsung)",
    # Chinese/HK ADRs
    "BABA": "China (Alibaba)",
    "JD": "China (JD.com)",
    "PDD": "China (PDD Holdings)",
    "BIDU": "China (Baidu)",
    "NIO": "China (NIO)",
    "LI": "China (Li Auto)",
    "XPEV": "China (XPeng)",
    "TCEHY": "China (Tencent)",
    # Australian ADRs
    "BHP": "Australia (BHP)",
    "RIO": "Australia (Rio Tinto)",
}


# ---------------------------------------------------------------------------
# Day-of-Week Check
# ---------------------------------------------------------------------------


def is_asia_note_day() -> bool:
    """
    Check if today is Sunday through Thursday (the days when Asia
    markets open that night / next morning).

    The Asia note fires at 21:45 ET Sun-Thu because Asian markets open
    during the US evening hours.

    Returns:
        True if today is Sunday (6), Monday (0), Tuesday (1),
        Wednesday (2), or Thursday (3).
    """
    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)
    except ImportError:
        # Fallback: use local time (assumes ET on Mac Mini)
        now_et = datetime.now()

    # weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    return now_et.weekday() in (0, 1, 2, 3, 6)  # Mon-Thu + Sunday


# ---------------------------------------------------------------------------
# Price Fetching
# ---------------------------------------------------------------------------


def fetch_asia_prices() -> dict[str, Optional[float]]:
    """
    Fetch latest prices for Asia-relevant instruments via yfinance.

    Returns a dict mapping descriptive keys to prices (or None if unavailable).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not available — cannot fetch Asia prices")
        return {}

    prices: dict[str, Optional[float]] = {}

    for key, ticker in ASIA_TICKERS.items():
        try:
            data = yf.download(
                ticker,
                period="2d",
                progress=False,
                auto_adjust=True,
            )
            if data.empty:
                prices[key] = None
                continue

            # yfinance 1.2+ returns MultiIndex columns even for single ticker
            if hasattr(data.columns, "levels"):
                data.columns = data.columns.get_level_values(0)

            close = data["Close"].iloc[-1]
            prices[key] = float(close) if close == close else None  # NaN check
        except Exception as e:
            logger.warning(f"Failed to fetch {ticker} ({key}): {e}")
            prices[key] = None

    return prices


def get_book_adr_tickers() -> list[str]:
    """
    Read book.json and return any position tickers that have
    Asian ADR exposure.
    """
    book = load_book()
    positions = book.get("positions", [])
    adr_tickers = []

    for pos in positions:
        if pos.get("status") != "active":
            continue
        ticker = pos.get("ticker", "")
        if ticker in ADR_EXPOSURE:
            adr_tickers.append(ticker)

    return adr_tickers


# ---------------------------------------------------------------------------
# LLM-Based Note Generation
# ---------------------------------------------------------------------------


def generate_llm_note(prices: dict[str, Optional[float]], adr_tickers: list[str]) -> Optional[str]:
    """
    Use OpenRouter API to generate an 8-line Asia session preview.

    Returns the generated note text, or None if LLM is unavailable.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    # Build context for the LLM
    price_context = _format_prices_for_prompt(prices)
    adr_context = ""
    if adr_tickers:
        adr_lines = [f"  - {t}: {ADR_EXPOSURE.get(t, 'Asia exposure')}" for t in adr_tickers]
        adr_context = f"\nBook names with Asia ADR exposure:\n" + "\n".join(adr_lines)

    prompt = f"""You are a macro strategist writing a concise Asia session preview for a portfolio manager.
Generate exactly 8 lines or fewer. Cover:
1. Japan/Korea/Australia first session outlook
2. China/HK open expectations
3. USDJPY and CNH tone
4. US futures reaction
5. Any implications for book names with Asia exposure

Current market data:
{price_context}
{adr_context}

Write in terse desk-note style. No headers, no bullet symbols. Each line should be a complete thought.
Keep it to 8 lines maximum. Start directly with content — no greeting or sign-off."""

    # Call LLM through OpenClaw gateway
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from data_platform.llm import call_llm

    content = call_llm(message=prompt, timeout=60)

    if content:
        # Enforce 8-line limit
        lines = content.strip().split("\n")
        return "\n".join(lines[:8])
    return None


# ---------------------------------------------------------------------------
# Template-Based Fallback
# ---------------------------------------------------------------------------


def generate_template_note(prices: dict[str, Optional[float]], adr_tickers: list[str]) -> str:
    """
    Generate a data-only template message when LLM is unavailable.

    Returns an 8-line-max note from raw price data.
    """
    lines: list[str] = []

    # Line 1: Header
    try:
        import pytz
        et = pytz.timezone("US/Eastern")
        now_et = datetime.now(et)
    except ImportError:
        now_et = datetime.now()
    lines.append(f"ASIA OPEN NOTE — {now_et.strftime('%a %d %b %H:%M ET')}")

    # Line 2: Japan/Korea/Australia
    nk = _fmt_price(prices.get("nikkei"))
    ks = _fmt_price(prices.get("kospi"))
    ax = _fmt_price(prices.get("asx"))
    lines.append(f"Nikkei {nk} | KOSPI {ks} | ASX200 {ax}")

    # Line 3: China/HK
    hsi = _fmt_price(prices.get("hsi"))
    lines.append(f"HSI {hsi}")

    # Line 4: FX
    jpy = _fmt_price(prices.get("usdjpy"), decimals=2)
    cnh = _fmt_price(prices.get("usdcnh"), decimals=4)
    lines.append(f"USDJPY {jpy} | USDCNH {cnh}")

    # Line 5: US Futures
    es = _fmt_price(prices.get("es_futures"))
    lines.append(f"ES futures {es}")

    # Line 6-7: Book ADR exposure (if any)
    if adr_tickers:
        adr_str = ", ".join(f"{t} ({ADR_EXPOSURE.get(t, 'Asia')})" for t in adr_tickers[:3])
        lines.append(f"Book Asia exposure: {adr_str}")
    else:
        lines.append("No book names with direct Asia ADR exposure")

    # Line 8: Status
    lines.append("Data-only note (no LLM available)")

    return "\n".join(lines[:8])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_price(value: Optional[float], decimals: int = 1) -> str:
    """Format a price for display, or show 'N/A' if unavailable."""
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def _format_prices_for_prompt(prices: dict[str, Optional[float]]) -> str:
    """Format price data as context for the LLM prompt."""
    labels = {
        "nikkei": "Nikkei 225",
        "kospi": "KOSPI",
        "asx": "ASX 200",
        "hsi": "Hang Seng",
        "usdjpy": "USD/JPY",
        "usdcnh": "USD/CNH",
        "es_futures": "S&P 500 E-mini Futures",
    }
    lines = []
    for key, label in labels.items():
        val = prices.get(key)
        if val is not None:
            lines.append(f"  {label}: {val:,.2f}")
        else:
            lines.append(f"  {label}: unavailable")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Asia open note entry point.

    1. Check that it's Sun-Thu (skip otherwise)
    2. Fetch relevant market data
    3. Read book.json for Asian ADR exposure
    4. Generate note (LLM if available, template fallback)
    5. Deliver via Telegram
    6. Log cycle
    """
    cycle_start = time.time()

    # Step 1: Day check (Requirement 6.1 — Sun through Thu)
    if not is_asia_note_day():
        logger.info("Skipping Asia note — not Sun-Thu.")
        log_cycle(
            cycle_type="asia_note",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_sun_thu"},
            trigger_source="launchd",
        )
        return

    logger.info("Generating Asia open note...")

    # Step 2: Fetch market data
    prices = fetch_asia_prices()
    data_available = sum(1 for v in prices.values() if v is not None)
    logger.info(f"Fetched prices: {data_available}/{len(ASIA_TICKERS)} available")

    # Step 3: Check book for ADR exposure
    adr_tickers = get_book_adr_tickers()
    if adr_tickers:
        logger.info(f"Book ADR exposure: {', '.join(adr_tickers)}")

    # Step 4: Generate note (LLM or fallback)
    note = generate_llm_note(prices, adr_tickers)
    generation_method = "llm"

    if note is None:
        # Graceful degradation: template-based fallback
        note = generate_template_note(prices, adr_tickers)
        generation_method = "template"
        logger.info("Using template-based note (no LLM available)")
    else:
        logger.info("Generated LLM-based Asia note")

    # Enforce 8-line limit (Requirement 6.3)
    note_lines = note.strip().split("\n")
    if len(note_lines) > 8:
        note = "\n".join(note_lines[:8])
        logger.warning(f"Trimmed note from {len(note_lines)} to 8 lines")

    # Step 5: Deliver via Telegram (Requirement 6.4)
    logger.info("Delivering via Telegram...")
    delivery_success = send_message(note)

    duration = time.time() - cycle_start

    if delivery_success:
        logger.info(f"Asia note delivered successfully in {duration:.1f}s")
    else:
        logger.error("Telegram delivery failed")

    # Step 6: Log cycle
    log_cycle(
        cycle_type="asia_note",
        status="success" if delivery_success else "failure",
        duration_seconds=duration,
        metrics={
            "generation_method": generation_method,
            "prices_available": data_available,
            "total_tickers": len(ASIA_TICKERS),
            "adr_tickers": adr_tickers,
            "note_lines": len(note.strip().split("\n")),
            "delivery_success": delivery_success,
        },
        error="Telegram delivery failed" if not delivery_success else None,
        trigger_source="launchd",
    )


if __name__ == "__main__":
    main()
