#!/usr/bin/env python3
"""
Daily Sweep — runs weekdays at 06:00 ET via launchd.

Triggers a filtered agent pipeline run focused on sectors with active positions.
If no positions exist, runs a reduced set of macro agents only.

Workflow:
  1. Check is_trading_day() — skip and log if holiday
  2. Read book.json to find active position tickers
  3. Map tickers to sectors → fund_* agent IDs + relevant macro_* agents
  4. If no active positions, run macro_northamerica, macro_westerneurope, macro_asia only
  5. Invoke run_cycle.py --agents <filtered_list>
  6. Log structured cycle entry on completion or failure

Requirements: 11.1, 11.2, 11.3, 11.4, 11.6, 11.7
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.book_ops import load_book
from src.data_platform.cycle_logger import log_cycle
from src.data_platform.market_calendar import is_trading_day

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_sweep")

# ---------------------------------------------------------------------------
# Sector → Agent Mapping
# ---------------------------------------------------------------------------

# Maps GICS-style sector labels to fund_* agent IDs
SECTOR_TO_AGENT: dict[str, str] = {
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

# Maps individual tickers to their sector (lowercase)
# Sourced from the POC_TICKERS universe in run_cycle.py
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

# Sector → relevant macro agents (sectors may have regional macro exposure)
SECTOR_TO_MACRO: dict[str, list[str]] = {
    "energy": ["macro_northamerica", "macro_commodities"],
    "information technology": ["macro_northamerica"],
    "healthcare": ["macro_northamerica"],
    "financials": ["macro_northamerica"],
    "materials": ["macro_northamerica", "macro_commodities"],
    "industrials": ["macro_northamerica", "macro_westerneurope"],
    "consumer discretionary": ["macro_northamerica", "macro_asia"],
    "consumer staples": ["macro_northamerica"],
    "communication services": ["macro_northamerica"],
    "utilities": ["macro_northamerica"],
    "real estate": ["macro_northamerica"],
}

# Reduced set of macro agents when no active positions
DEFAULT_MACRO_AGENTS = [
    "macro_northamerica",
    "macro_westerneurope",
    "macro_asia",
]

# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------


def get_active_sectors() -> list[str]:
    """
    Read book.json, find active position tickers, and map them to sectors.

    Returns a deduplicated list of sector names (lowercase) that have at
    least one active position.
    """
    book = load_book()
    positions = book.get("positions", [])

    sectors: set[str] = set()
    for pos in positions:
        if pos.get("status") != "active":
            continue

        # Check primary ticker
        ticker = pos.get("ticker", "")
        if ticker in TICKER_TO_SECTOR:
            sectors.add(TICKER_TO_SECTOR[ticker])

        # Check hedge ticker (it may be in a different sector — but typically
        # the hedge is the EW sector ETF, so same sector)
        hedge_ticker = pos.get("hedge_ticker", "")
        if hedge_ticker in TICKER_TO_SECTOR:
            sectors.add(TICKER_TO_SECTOR[hedge_ticker])

    return sorted(sectors)


def get_relevant_agents(sectors: list[str]) -> list[str]:
    """
    Map sectors to fund_* agent IDs, plus relevant macro_* agents.

    For each active sector:
      - Include the sector's fund_* agent
      - Include macro agents relevant to that sector

    Always includes macro_northamerica as the baseline domestic macro agent.

    Returns a deduplicated, sorted list of agent IDs.
    """
    agents: set[str] = set()

    for sector in sectors:
        # Add the sector's fundamental agent
        fund_agent = SECTOR_TO_AGENT.get(sector)
        if fund_agent:
            agents.add(fund_agent)

        # Add relevant macro agents for this sector
        macro_agents = SECTOR_TO_MACRO.get(sector, [])
        agents.update(macro_agents)

    # Always include macro_northamerica as baseline
    agents.add("macro_northamerica")

    return sorted(agents)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Daily sweep entry point.

    1. Check if today is a trading day — skip if holiday/weekend
    2. Determine which agents to run based on active positions
    3. Invoke run_cycle.py with the agent filter
    4. Log structured cycle entry
    """
    cycle_start = time.time()

    # Requirement 11.6: Skip on holidays
    if not is_trading_day():
        logger.info("Skipping daily sweep — not a trading day (holiday or weekend).")
        log_cycle(
            cycle_type="daily_sweep",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_trading_day"},
            trigger_source="launchd",
        )
        return

    # Determine which agents to run
    sectors = get_active_sectors()

    if not sectors:
        # Requirement 11.3: No active positions → run macro agents only
        agents = DEFAULT_MACRO_AGENTS[:]
        logger.info(
            "No active positions in book. Running macro agents only: "
            f"{', '.join(agents)}"
        )
    else:
        agents = get_relevant_agents(sectors)
        logger.info(
            f"Active sectors: {', '.join(sectors)}. "
            f"Running agents: {', '.join(agents)}"
        )

    # Invoke run_cycle.py with the agent filter
    run_cycle_path = PROJECT_ROOT / "run_cycle.py"
    cmd = [
        sys.executable,
        str(run_cycle_path),
        "--agents", ",".join(agents),
    ]

    logger.info(f"Invoking: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )

        duration = time.time() - cycle_start

        if result.returncode == 0:
            logger.info(
                f"Daily sweep completed successfully in {duration:.1f}s."
            )
            log_cycle(
                cycle_type="daily_sweep",
                status="success",
                duration_seconds=duration,
                metrics={
                    "agents_run": len(agents),
                    "agent_list": agents,
                    "sectors_active": sectors,
                },
                trigger_source="launchd",
            )
        else:
            # Requirement 11.7: Log failure with error details
            logger.error(
                f"Daily sweep failed (exit code {result.returncode}). "
                f"stderr: {result.stderr[:500]}"
            )
            log_cycle(
                cycle_type="daily_sweep",
                status="failure",
                duration_seconds=duration,
                metrics={
                    "agents_run": len(agents),
                    "agent_list": agents,
                    "exit_code": result.returncode,
                },
                error=result.stderr[:2000] if result.stderr else "Non-zero exit code",
                trigger_source="launchd",
            )

    except subprocess.TimeoutExpired:
        duration = time.time() - cycle_start
        logger.error("Daily sweep timed out after 1 hour.")
        log_cycle(
            cycle_type="daily_sweep",
            status="failure",
            duration_seconds=duration,
            metrics={
                "agents_run": len(agents),
                "agent_list": agents,
            },
            error="Timeout: exceeded 3600s limit",
            trigger_source="launchd",
        )

    except Exception as e:
        duration = time.time() - cycle_start
        logger.error(f"Daily sweep encountered unexpected error: {e}")
        log_cycle(
            cycle_type="daily_sweep",
            status="failure",
            duration_seconds=duration,
            metrics={
                "agents_run": len(agents),
                "agent_list": agents,
            },
            error=str(e),
            trigger_source="launchd",
        )


if __name__ == "__main__":
    main()
