# Feature: live-data-automated-recommendations, Property 3: Daily Sweep Agent Selection
"""
Property-based tests for scripts/daily_sweep.py — agent selection logic.

Property 3: Daily Sweep Agent Selection
For any book state containing active positions, the daily sweep agent filter SHALL
include exactly the fund_* agents whose sectors contain at least one active position
ticker, plus the macro agents relevant to those sectors. For any book state with no
active positions, the filter SHALL return only a reduced set of macro agents.

**Validates: Requirements 11.2, 11.3**
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Load daily_sweep module from scripts directory
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("daily_sweep", _SCRIPTS_DIR / "daily_sweep.py")
daily_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_sweep)

# Extract the mappings from the module as the test oracle
TICKER_TO_SECTOR = daily_sweep.TICKER_TO_SECTOR
SECTOR_TO_AGENT = daily_sweep.SECTOR_TO_AGENT
SECTOR_TO_MACRO = daily_sweep.SECTOR_TO_MACRO
DEFAULT_MACRO_AGENTS = daily_sweep.DEFAULT_MACRO_AGENTS

# All tickers known to the system
ALL_TICKERS = list(TICKER_TO_SECTOR.keys())

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: a list of tickers representing active positions in the book
# Using st.lists with sampled_from the known ticker universe
active_tickers_strategy = st.lists(
    st.sampled_from(ALL_TICKERS),
    min_size=1,
    max_size=20,
)

# Strategy: an empty list (no active positions)
empty_tickers_strategy = st.just([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_mock_book(tickers: list[str]) -> dict:
    """Construct a mock book.json structure with the given tickers as active positions."""
    positions = [
        {"ticker": t, "hedge_ticker": "", "status": "active"}
        for t in tickers
    ]
    return {"positions": positions}


def compute_expected_agents(tickers: list[str]) -> set[str]:
    """
    Test oracle: independently compute what agents should be selected
    for a given list of active position tickers.
    """
    sectors: set[str] = set()
    for ticker in tickers:
        if ticker in TICKER_TO_SECTOR:
            sectors.add(TICKER_TO_SECTOR[ticker])

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

    return agents


# ---------------------------------------------------------------------------
# Property 3: Daily Sweep Agent Selection — Non-Empty Book
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tickers=active_tickers_strategy)
def test_property_3_active_positions_select_correct_agents(tickers: list[str]):
    """
    **Validates: Requirements 11.2, 11.3**

    Property 3: For any book with active positions, the agent filter includes
    exactly the fund_* agents for those sectors + relevant macro agents.
    """
    mock_book = build_mock_book(tickers)

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    agents = daily_sweep.get_relevant_agents(sectors)

    expected = compute_expected_agents(tickers)

    assert set(agents) == expected


# ---------------------------------------------------------------------------
# Property 3: Daily Sweep Agent Selection — Empty Book
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data())
def test_property_3_empty_book_returns_default_macro_only(data):
    """
    **Validates: Requirements 11.2, 11.3**

    Property 3: For any book with no active positions, the filter returns
    only the reduced set of macro agents (macro_northamerica, macro_westerneurope,
    macro_asia).
    """
    mock_book = {"positions": []}

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    # With no active sectors, daily_sweep.main() uses DEFAULT_MACRO_AGENTS
    assert sectors == []

    # Verify that the default agent set is the expected reduced macro set
    expected_default = {"macro_northamerica", "macro_westerneurope", "macro_asia"}
    assert set(DEFAULT_MACRO_AGENTS) == expected_default


# ---------------------------------------------------------------------------
# Property 3 sub-property: Every active sector produces its fund_* agent
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tickers=active_tickers_strategy)
def test_property_3_every_active_sector_has_fund_agent(tickers: list[str]):
    """
    **Validates: Requirements 11.2**

    Sub-property of Property 3: For every sector with an active position,
    the corresponding fund_* agent is present in the result.
    """
    mock_book = build_mock_book(tickers)

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    agents = daily_sweep.get_relevant_agents(sectors)
    agent_set = set(agents)

    for sector in sectors:
        fund_agent = SECTOR_TO_AGENT.get(sector)
        if fund_agent:
            assert fund_agent in agent_set, (
                f"Sector '{sector}' is active but fund agent '{fund_agent}' "
                f"is missing from agent list: {agents}"
            )


# ---------------------------------------------------------------------------
# Property 3 sub-property: No spurious fund_* agents included
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tickers=active_tickers_strategy)
def test_property_3_no_spurious_fund_agents(tickers: list[str]):
    """
    **Validates: Requirements 11.2**

    Sub-property of Property 3: No fund_* agent is included unless its sector
    has at least one active position ticker.
    """
    mock_book = build_mock_book(tickers)

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    agents = daily_sweep.get_relevant_agents(sectors)
    active_sector_set = set(sectors)

    # Collect fund_* agents that are in the result
    fund_agents_in_result = [a for a in agents if a.startswith("fund_")]

    # Reverse map: agent -> sector
    agent_to_sector = {v: k for k, v in SECTOR_TO_AGENT.items()}

    for fund_agent in fund_agents_in_result:
        sector = agent_to_sector.get(fund_agent)
        assert sector in active_sector_set, (
            f"Fund agent '{fund_agent}' (sector: '{sector}') is in the result "
            f"but the sector has no active positions. Active sectors: {sectors}"
        )


# ---------------------------------------------------------------------------
# Property 3 sub-property: macro_northamerica always present
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tickers=active_tickers_strategy)
def test_property_3_macro_northamerica_always_present(tickers: list[str]):
    """
    **Validates: Requirements 11.2**

    Sub-property of Property 3: macro_northamerica is always included in the
    agent list regardless of which sectors are active (baseline domestic macro).
    """
    mock_book = build_mock_book(tickers)

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    agents = daily_sweep.get_relevant_agents(sectors)

    assert "macro_northamerica" in agents


# ---------------------------------------------------------------------------
# Property 3 sub-property: Result is deduplicated and sorted
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(tickers=active_tickers_strategy)
def test_property_3_result_is_deduplicated_and_sorted(tickers: list[str]):
    """
    **Validates: Requirements 11.2**

    Sub-property of Property 3: get_relevant_agents returns a deduplicated,
    sorted list (no duplicate entries).
    """
    mock_book = build_mock_book(tickers)

    with patch.object(daily_sweep, "load_book", return_value=mock_book):
        sectors = daily_sweep.get_active_sectors()

    agents = daily_sweep.get_relevant_agents(sectors)

    # No duplicates
    assert len(agents) == len(set(agents)), f"Duplicate agents found: {agents}"

    # Sorted
    assert agents == sorted(agents), f"Agents not sorted: {agents}"
