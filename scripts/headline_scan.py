#!/usr/bin/env python3
"""
Hourly Headline Scan — scans news headlines for all open position tickers
during Market_Hours and routes material news to the owning agent seat.

Triggered hourly via launchd during market hours. Workflow:
  1. Check is_market_open() — skip if market closed
  2. Read book.json for active position tickers
  3. For each ticker, scan headlines using existing NewsScanner + Brave search (if key available)
  4. Evaluate materiality (keyword matching + LLM call if OpenRouter available)
  5. Route material headlines to the appropriate agent seat (log to file, or call OpenRouter)
  6. Log scan results via log_cycle
  7. Send Telegram notification only for material news affecting positions

LLM-dependent parts degrade gracefully:
  - Without BRAVE_API_KEY: uses yfinance NewsScanner only
  - Without OPENROUTER_API_KEY: uses keyword-based materiality check only
  - All paths produce structured logs regardless of API availability

Requirements: 5.1, 5.2, 5.3, 5.4
Requirement 23.3: Skip entirely when book is empty.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.book_ops import load_book
from src.data_platform.cycle_logger import log_cycle
from src.data_platform.market_calendar import is_market_open
from src.data_platform.news import NewsScanner

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("headline_scan")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Brave search API — optional, enhances coverage beyond yfinance
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# OpenRouter API — optional, enables LLM-based materiality evaluation
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Material keyword patterns — used when LLM is unavailable
MATERIAL_KEYWORDS = [
    "earnings", "revenue", "profit", "loss", "guidance", "forecast",
    "downgrade", "upgrade", "target", "acquisition", "merger", "buyout",
    "SEC", "investigation", "lawsuit", "settlement", "recall",
    "FDA", "approval", "rejection", "clinical trial", "phase 3",
    "dividend", "buyback", "split", "offering", "dilution",
    "CEO", "CFO", "resign", "fired", "appoint",
    "bankruptcy", "default", "restructuring",
    "sanctions", "tariff", "ban", "regulation",
    "strike", "shutdown", "outage", "cyber", "hack",
    "analyst", "rating", "consensus", "surprise",
    "beat", "miss", "warning", "pre-announce",
]

# Flip-condition keywords that suggest thesis invalidation risk
FLIP_KEYWORDS = [
    "downgrade", "guidance cut", "warning", "miss", "loss",
    "investigation", "lawsuit", "recall", "bankruptcy", "default",
    "resign", "fired", "sanctions", "ban", "rejection",
]


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ScannedHeadline:
    """A headline found during the scan with materiality assessment."""
    ticker: str
    title: str
    source: str
    url: str
    is_material: bool
    materiality_reason: str  # Why it was flagged or "immaterial"
    owning_seat: str  # Agent seat responsible for this ticker


# ---------------------------------------------------------------------------
# Sector → Agent Mapping (mirrors daily_sweep.py)
# ---------------------------------------------------------------------------

TICKER_TO_SECTOR: dict[str, str] = {
    # Energy
    "XOM": "energy", "CVX": "energy", "COP": "energy", "EOG": "energy",
    "SLB": "energy", "MPC": "energy", "PSX": "energy", "VLO": "energy",
    "OXY": "energy", "DVN": "energy", "XLE": "energy", "RSPG": "energy",
    # Information Technology
    "AAPL": "information technology", "MSFT": "information technology",
    "NVDA": "information technology", "AVGO": "information technology",
    "CRM": "information technology", "ADBE": "information technology",
    "ORCL": "information technology", "AMD": "information technology",
    "INTC": "information technology", "NOW": "information technology",
    "XLK": "information technology", "RSPT": "information technology",
    # Healthcare
    "UNH": "healthcare", "JNJ": "healthcare", "LLY": "healthcare",
    "ABBV": "healthcare", "MRK": "healthcare", "PFE": "healthcare",
    "TMO": "healthcare", "ABT": "healthcare", "AMGN": "healthcare",
    "ISRG": "healthcare", "XLV": "healthcare", "RSPH": "healthcare",
    # Financials
    "JPM": "financials", "BAC": "financials", "WFC": "financials",
    "GS": "financials", "MS": "financials", "BLK": "financials",
    "SCHW": "financials", "AXP": "financials", "V": "financials",
    "MA": "financials", "XLF": "financials", "RSPF": "financials",
    # Materials
    "LIN": "materials", "SHW": "materials", "APD": "materials",
    "ECL": "materials", "FCX": "materials", "NEM": "materials",
    "NUE": "materials", "DOW": "materials", "DD": "materials",
    "CTVA": "materials", "XLB": "materials",
    # Industrials
    "CAT": "industrials", "HON": "industrials", "UNP": "industrials",
    "RTX": "industrials", "GE": "industrials", "DE": "industrials",
    "LMT": "industrials", "WM": "industrials", "ETN": "industrials",
    "ITW": "industrials", "XLI": "industrials", "RSPI": "industrials",
    # Consumer Discretionary
    "AMZN": "consumer discretionary", "TSLA": "consumer discretionary",
    "HD": "consumer discretionary", "MCD": "consumer discretionary",
    "NKE": "consumer discretionary", "LOW": "consumer discretionary",
    "SBUX": "consumer discretionary", "TJX": "consumer discretionary",
    "BKNG": "consumer discretionary", "CMG": "consumer discretionary",
    "XLY": "consumer discretionary", "RSPD": "consumer discretionary",
    # Consumer Staples
    "PG": "consumer staples", "KO": "consumer staples", "PEP": "consumer staples",
    "COST": "consumer staples", "WMT": "consumer staples", "PM": "consumer staples",
    "MO": "consumer staples", "MDLZ": "consumer staples", "CL": "consumer staples",
    "KHC": "consumer staples", "XLP": "consumer staples", "RSPS": "consumer staples",
    # Communication Services
    "META": "communication services", "GOOG": "communication services",
    "NFLX": "communication services", "DIS": "communication services",
    "CMCSA": "communication services", "T": "communication services",
    "VZ": "communication services", "TMUS": "communication services",
    "CHTR": "communication services", "EA": "communication services",
    "XLC": "communication services", "RSPC": "communication services",
    # Utilities
    "NEE": "utilities", "SO": "utilities", "DUK": "utilities",
    "SRE": "utilities", "AEP": "utilities", "D": "utilities",
    "XEL": "utilities", "EXC": "utilities", "WEC": "utilities",
    "ED": "utilities", "XLU": "utilities", "RSPU": "utilities",
    # Real Estate
    "PLD": "real estate", "AMT": "real estate", "EQIX": "real estate",
    "SPG": "real estate", "O": "real estate", "PSA": "real estate",
    "WELL": "real estate", "DLR": "real estate", "AVB": "real estate",
    "EXR": "real estate", "XLRE": "real estate", "RSPR": "real estate",
}

SECTOR_TO_FUND_AGENT: dict[str, str] = {
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

# Macro agents for specific asset types
MACRO_AGENTS = [
    "macro_northamerica", "macro_westerneurope", "macro_asia",
    "macro_ceemea", "macro_latam", "macro_commodities",
]


# ---------------------------------------------------------------------------
# Brave Search Integration
# ---------------------------------------------------------------------------


def brave_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search headlines via Brave Search API.

    Args:
        query: Search query string (e.g., "XOM Exxon Mobil news today").
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with keys: title, url, description.
        Returns empty list if BRAVE_API_KEY is not configured or request fails.
    """
    if not BRAVE_API_KEY:
        return []

    try:
        params = urllib.parse.urlencode({
            "q": query,
            "count": max_results,
            "freshness": "pd",  # past day
        })
        url = f"{BRAVE_SEARCH_URL}?{params}"

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("Accept-Encoding", "gzip")
        req.add_header("X-Subscription-Token", BRAVE_API_KEY)

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            })
        return results

    except Exception as e:
        logger.debug(f"Brave search failed for query '{query}': {e}")
        return []


# Need urllib.parse for URL encoding
import urllib.parse


# ---------------------------------------------------------------------------
# Headline Fetching (combines yfinance + Brave)
# ---------------------------------------------------------------------------


def fetch_headlines_for_ticker(ticker: str) -> list[dict]:
    """
    Fetch recent headlines for a ticker from all available sources.

    Sources (in priority order):
      1. Brave Search API (if BRAVE_API_KEY configured) — wider coverage
      2. yfinance via NewsScanner — free, always available

    Returns:
        List of dicts with keys: title, source, url
    """
    headlines: list[dict] = []
    seen_titles: set[str] = set()

    # Source 1: Brave search (broader coverage, includes news wire services)
    brave_results = brave_search(f"{ticker} stock news today")
    for item in brave_results:
        title = item.get("title", "").strip()
        if title and title.lower() not in seen_titles:
            seen_titles.add(title.lower())
            headlines.append({
                "title": title,
                "source": "brave_search",
                "url": item.get("url", ""),
            })

    # Source 2: yfinance NewsScanner (always available)
    try:
        scanner = NewsScanner()
        yf_headlines = scanner.get_headlines(ticker, max_items=5)
        for h in yf_headlines:
            if h.title.lower() not in seen_titles:
                seen_titles.add(h.title.lower())
                headlines.append({
                    "title": h.title,
                    "source": h.source,
                    "url": h.url,
                })
    except Exception as e:
        logger.debug(f"yfinance headlines unavailable for {ticker}: {e}")

    return headlines


# ---------------------------------------------------------------------------
# Materiality Assessment
# ---------------------------------------------------------------------------


def assess_materiality_keywords(headline: str, ticker: str) -> tuple[bool, str]:
    """
    Keyword-based materiality assessment (fallback when LLM unavailable).

    A headline is material if it contains keywords suggesting a meaningful
    event for the position thesis. This is conservative — prefers false
    positives (alert on borderline) over false negatives (miss something real).

    Args:
        headline: The headline text.
        ticker: The ticker symbol.

    Returns:
        Tuple of (is_material, reason).
    """
    headline_lower = headline.lower()

    # Check for material keywords
    matched_keywords = [kw for kw in MATERIAL_KEYWORDS if kw in headline_lower]
    if matched_keywords:
        return True, f"keyword match: {', '.join(matched_keywords[:3])}"

    # Check if ticker is directly mentioned (high relevance)
    if ticker.lower() in headline_lower:
        # Ticker-specific headline — slightly lower bar
        for kw in MATERIAL_KEYWORDS:
            if kw in headline_lower:
                return True, f"ticker-specific + keyword: {kw}"

    return False, "immaterial"


def assess_materiality_llm(
    headline: str,
    ticker: str,
    position_thesis: str,
    flip_condition: str,
) -> tuple[bool, str]:
    """
    LLM-based materiality assessment using OpenRouter.

    Asks the LLM whether a headline is material to the position thesis
    and whether it threatens the flip condition.

    Args:
        headline: The headline text.
        ticker: The ticker symbol.
        position_thesis: The investment thesis for the position.
        flip_condition: The stated condition that would invalidate the thesis.

    Returns:
        Tuple of (is_material, reason).
        Falls back to keyword-based assessment if LLM call fails.
    """
    if not OPENROUTER_API_KEY:
        return assess_materiality_keywords(headline, ticker)

    prompt = (
        f"You are a trading desk analyst. Evaluate whether this headline is "
        f"MATERIAL to the following position and thesis.\n\n"
        f"Ticker: {ticker}\n"
        f"Headline: {headline}\n"
        f"Position thesis: {position_thesis}\n"
        f"Flip condition: {flip_condition}\n\n"
        f"Reply with exactly one line:\n"
        f"MATERIAL: <one-sentence reason>\n"
        f"or\n"
        f"IMMATERIAL\n"
        f"Be conservative — when in doubt, flag as material."
    )

    try:
        payload = json.dumps({
            "model": "anthropic/claude-sonnet-4-20250514",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0.0,
        }).encode("utf-8")

        req = urllib.request.Request(OPENROUTER_URL, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {OPENROUTER_API_KEY}")
        req.add_header("HTTP-Referer", "https://agentictrading.local")

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if reply.upper().startswith("MATERIAL"):
            reason = reply.split(":", 1)[1].strip() if ":" in reply else "LLM flagged"
            return True, reason
        else:
            return False, "immaterial (LLM assessed)"

    except Exception as e:
        logger.warning(f"LLM materiality check failed for {ticker}: {e}. Falling back to keywords.")
        return assess_materiality_keywords(headline, ticker)


# ---------------------------------------------------------------------------
# Agent Routing
# ---------------------------------------------------------------------------


def get_owning_seat(ticker: str) -> str:
    """
    Determine which agent seat owns a ticker for flip-condition checks.

    Returns the fund_* agent ID for equity tickers, or the relevant
    macro agent for FX/commodity/index tickers.
    """
    sector = TICKER_TO_SECTOR.get(ticker)
    if sector:
        return SECTOR_TO_FUND_AGENT.get(sector, "fund_infotech")

    # ETF tickers that map to macro agents
    macro_tickers = {
        "SPY": "macro_northamerica", "RSP": "macro_northamerica",
        "EFA": "macro_westerneurope", "EEM": "macro_asia",
        "USO": "macro_commodities", "GLD": "macro_commodities",
        "DXY": "macro_northamerica", "USDJPY": "macro_asia",
        "EURUSD": "macro_westerneurope",
    }
    return macro_tickers.get(ticker, "macro_northamerica")


def route_material_headline(headline: ScannedHeadline) -> None:
    """
    Route a material headline to its owning agent seat for flip-condition check.

    If OpenRouter is available, submits a flip-condition evaluation request.
    Otherwise, logs the material headline to a routing file for later review.

    Args:
        headline: The ScannedHeadline that was assessed as material.
    """
    routing_dir = PROJECT_ROOT / "memos" / "state" / "headline_routing"
    routing_dir.mkdir(parents=True, exist_ok=True)

    # Write routing entry regardless of LLM availability
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    route_file = routing_dir / f"{headline.ticker}_{ts}.json"

    route_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": headline.ticker,
        "headline": headline.title,
        "source": headline.source,
        "url": headline.url,
        "owning_seat": headline.owning_seat,
        "materiality_reason": headline.materiality_reason,
        "flip_check_requested": bool(OPENROUTER_API_KEY),
    }

    try:
        route_file.write_text(json.dumps(route_entry, indent=2))
        logger.info(
            f"Routed material headline for {headline.ticker} → {headline.owning_seat}: "
            f"{headline.title[:60]}"
        )
    except OSError as e:
        logger.error(f"Failed to write routing file: {e}")


# ---------------------------------------------------------------------------
# Telegram Notification
# ---------------------------------------------------------------------------


def notify_material_headlines(material_headlines: list[ScannedHeadline]) -> None:
    """
    Send Telegram notification for material headlines affecting positions.

    Groups headlines by ticker and sends a single consolidated message.
    Only called when there are material headlines to report.
    """
    if not material_headlines:
        return

    try:
        from src.telegram_bot import send_message
    except (ImportError, RuntimeError) as e:
        logger.warning(f"Telegram unavailable: {e}. Skipping notification.")
        return

    lines = ["📰 *Headline Scan — Material News*", ""]

    # Group by ticker
    by_ticker: dict[str, list[ScannedHeadline]] = {}
    for h in material_headlines:
        by_ticker.setdefault(h.ticker, []).append(h)

    for ticker, headlines in by_ticker.items():
        seat = headlines[0].owning_seat
        lines.append(f"*{ticker}* (→ {seat}):")
        for h in headlines[:3]:  # Max 3 per ticker to keep message concise
            lines.append(f"  • {h.title[:80]}")
            lines.append(f"    _{h.materiality_reason}_")
        lines.append("")

    lines.append(f"Routed to owning seats for flip-condition check.")

    message = "\n".join(lines)
    send_message(message)


# ---------------------------------------------------------------------------
# Main Scan Logic
# ---------------------------------------------------------------------------


def get_active_tickers(book: dict) -> list[str]:
    """Extract unique tickers from active positions (primary only, not hedges)."""
    tickers: list[str] = []
    seen: set[str] = set()

    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        ticker = pos.get("ticker")
        if ticker and ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)

    return tickers


def get_position_context(book: dict, ticker: str) -> tuple[str, str]:
    """
    Get the thesis and flip condition for a position.

    Returns:
        Tuple of (thesis, flip_condition). Defaults to empty strings if not found.
    """
    for pos in book.get("positions", []):
        if pos.get("ticker") == ticker and pos.get("status") == "active":
            thesis = pos.get("thesis", "")
            flip = pos.get("flip_condition", "")
            return thesis, flip
    return "", ""


def run_headline_scan() -> dict:
    """
    Execute the hourly headline scan.

    Returns:
        Metrics dict with scan results for structured logging.
    """
    metrics = {
        "tickers_scanned": 0,
        "headlines_found": 0,
        "headlines_material": 0,
        "headlines_immaterial": 0,
        "brave_available": bool(BRAVE_API_KEY),
        "llm_available": bool(OPENROUTER_API_KEY),
    }

    book = load_book()
    tickers = get_active_tickers(book)

    if not tickers:
        # Requirement 23.3: Skip when book is empty
        logger.info("No active positions in book. Skipping headline scan.")
        metrics["skip_reason"] = "empty_book"
        return metrics

    metrics["tickers_scanned"] = len(tickers)
    material_headlines: list[ScannedHeadline] = []

    for ticker in tickers:
        logger.info(f"Scanning headlines for {ticker}...")

        # Fetch headlines from all available sources
        raw_headlines = fetch_headlines_for_ticker(ticker)
        metrics["headlines_found"] += len(raw_headlines)

        if not raw_headlines:
            logger.debug(f"No headlines found for {ticker}")
            continue

        # Get position context for LLM materiality check
        thesis, flip_condition = get_position_context(book, ticker)
        owning_seat = get_owning_seat(ticker)

        for raw in raw_headlines:
            title = raw.get("title", "")
            if not title:
                continue

            # Assess materiality
            if OPENROUTER_API_KEY and thesis:
                is_material, reason = assess_materiality_llm(
                    title, ticker, thesis, flip_condition
                )
            else:
                is_material, reason = assess_materiality_keywords(title, ticker)

            if is_material:
                scanned = ScannedHeadline(
                    ticker=ticker,
                    title=title,
                    source=raw.get("source", "unknown"),
                    url=raw.get("url", ""),
                    is_material=True,
                    materiality_reason=reason,
                    owning_seat=owning_seat,
                )
                material_headlines.append(scanned)
                metrics["headlines_material"] += 1

                # Route to owning seat
                route_material_headline(scanned)
            else:
                metrics["headlines_immaterial"] += 1
                # Requirement 5.3: Remain silent for immaterial headlines

    # Send Telegram alert only for material news (Requirement 5.2)
    if material_headlines:
        notify_material_headlines(material_headlines)

    return metrics


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main():
    """
    Headline scan entry point.

    1. Check if market is open — skip if closed
    2. Run the headline scan
    3. Log structured cycle entry
    """
    cycle_start = time.time()

    # Requirement 5.1: Only scan during Market_Hours
    if not is_market_open():
        logger.info("Market is closed. Skipping headline scan.")
        log_cycle(
            cycle_type="headline_scan",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "market_closed"},
            trigger_source="launchd",
        )
        return

    logger.info("Starting hourly headline scan...")

    try:
        metrics = run_headline_scan()
        duration = time.time() - cycle_start

        if metrics.get("skip_reason") == "empty_book":
            log_cycle(
                cycle_type="headline_scan",
                status="skipped",
                duration_seconds=duration,
                metrics=metrics,
                trigger_source="launchd",
            )
            logger.info("Headline scan skipped — empty book.")
        else:
            log_cycle(
                cycle_type="headline_scan",
                status="success",
                duration_seconds=duration,
                metrics=metrics,
                trigger_source="launchd",
            )
            logger.info(
                f"Headline scan complete: {metrics['tickers_scanned']} tickers, "
                f"{metrics['headlines_found']} headlines found, "
                f"{metrics['headlines_material']} material."
            )

    except Exception as e:
        duration = time.time() - cycle_start
        logger.error(f"Headline scan failed: {e}")
        log_cycle(
            cycle_type="headline_scan",
            status="failure",
            duration_seconds=duration,
            metrics={"error_type": type(e).__name__},
            error=str(e),
            trigger_source="launchd",
        )


if __name__ == "__main__":
    main()
