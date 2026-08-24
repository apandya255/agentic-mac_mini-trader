# Feature: autonomous-trading-loop, Property 13: Auto-booked positions include full provenance
"""
Property-based tests for Phase 8 provenance logging in run_cycle.py.

Property 13: Auto-booked positions include full provenance
For any successfully auto-booked position, the corresponding trade journal entry
SHALL contain all provenance fields: proposal_id, debate_results, tech_score,
risk_decision, and pm_rationale. No provenance field SHALL be omitted.

**Validates: Requirements 1.3**
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies: generate random but valid order data that will pass all gates
# ---------------------------------------------------------------------------

# Conviction scores that pass the gate (>= 5)
passing_conviction = st.integers(min_value=5, max_value=10)

# Valid risk decisions that pass the gate
valid_risk_decisions = st.sampled_from(["approved", "approved_with_modifications"])

# Position size as fraction of NAV (realistic range)
size_pct_nav_strategy = st.floats(min_value=0.005, max_value=0.05, allow_nan=False, allow_infinity=False)

# Tickers: use a known set that the mocked price service will resolve
ticker_strategy = st.sampled_from(["XOM", "CVX", "MPC", "PSX", "EOG"])
hedge_ticker_strategy = st.sampled_from(["XLE", "RSPG"])

# Direction
direction_strategy = st.sampled_from(["long", "short"])

# Proposal IDs: alphanumeric identifiers
proposal_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_-"),
    min_size=3,
    max_size=30,
)

# PM rationale: non-empty text
pm_rationale_strategy = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# Debate results: list of debate round dicts
debate_result_entry = st.fixed_dictionaries({
    "agent_id": st.text(min_size=3, max_size=20),
    "stance": st.sampled_from(["support", "challenge", "neutral"]),
    "argument": st.text(min_size=5, max_size=100),
})
debate_results_strategy = st.one_of(
    st.lists(debate_result_entry, min_size=1, max_size=4),
    st.none(),
)

# Tech score: dict with a numeric score and optional fields
tech_score_strategy = st.one_of(
    st.fixed_dictionaries({
        "technical_score": st.integers(min_value=1, max_value=10),
        "trend_alignment": st.sampled_from(["aligned", "opposed", "neutral"]),
    }),
    st.none(),
)

# Risk decision as a dict (what comes from Phase 6)
risk_decision_dict_strategy = st.fixed_dictionaries({
    "decision": valid_risk_decisions,
    "rationale": st.text(min_size=1, max_size=100),
})


# ---------------------------------------------------------------------------
# Helper: simulate Phase 8 booking on a single order
# ---------------------------------------------------------------------------

MOCK_PRICES = {
    "XOM": 105.50,
    "CVX": 155.30,
    "MPC": 165.80,
    "PSX": 130.20,
    "EOG": 120.40,
    "XLE": 88.20,
    "RSPG": 72.10,
}


def run_phase_8_single_order(order: dict, tmp_path: Path) -> dict:
    """Run phase_8_update_book with a single order and return the resulting book."""
    import run_cycle

    state_dir = tmp_path / "memos" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    orders_dir = tmp_path / "memos" / "orders"
    orders_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "memos" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    proposals_dir = tmp_path / "memos" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    book = {
        "nav": 10_000_000,
        "initial_nav": 10_000_000,
        "cash_pct": 1.0,
        "session_open_nav": 10_000_000,
        "positions": [],
        "trade_journal": [],
    }
    book_path = state_dir / "book.json"
    book_path.write_text(json.dumps(book, indent=2))

    # Mock price service
    mock_price_service = MagicMock()
    mock_price_service.get_latest_close.side_effect = lambda t: MOCK_PRICES.get(t)
    mock_price_service_class = MagicMock(return_value=mock_price_service)

    with patch.object(run_cycle, "STATE_FILE", book_path), \
         patch.object(run_cycle, "MEMOS_DIR", tmp_path / "memos"), \
         patch.object(run_cycle, "LOG_DIR", tmp_path / "memos" / "logs"), \
         patch("data_platform.prices.PriceService", mock_price_service_class):
        run_cycle.phase_8_update_book([order])

    return json.loads(book_path.read_text())


# ---------------------------------------------------------------------------
# Property Test: Auto-booked positions include full provenance
# ---------------------------------------------------------------------------

REQUIRED_PROVENANCE_FIELDS = [
    "proposal_id",
    "debate_results",
    "tech_score",
    "risk_decision",
    "pm_rationale",
]


@given(
    ticker=ticker_strategy,
    hedge_ticker=hedge_ticker_strategy,
    direction=direction_strategy,
    conviction=passing_conviction,
    risk_decision_dict=risk_decision_dict_strategy,
    size_pct_nav=size_pct_nav_strategy,
    proposal_id=proposal_id_strategy,
    pm_rationale=pm_rationale_strategy,
    debate_results=debate_results_strategy,
    tech_score=tech_score_strategy,
)
@settings(max_examples=100, deadline=10000)
def test_property13_auto_booked_provenance_fields(
    ticker: str,
    hedge_ticker: str,
    direction: str,
    conviction: int,
    risk_decision_dict: dict,
    size_pct_nav: float,
    proposal_id: str,
    pm_rationale: str,
    debate_results,
    tech_score,
):
    """
    **Validates: Requirements 1.3**

    Property 13: Auto-booked positions include full provenance.
    For any order that passes all gates and gets booked, the trade journal
    entry SHALL contain all five provenance fields: proposal_id, debate_results,
    tech_score, risk_decision, pm_rationale.
    """
    # Ensure ticker != hedge_ticker for a realistic pair trade
    assume(ticker != hedge_ticker)

    # Create a fresh temp directory for each test run
    tmp_dir = Path(tempfile.mkdtemp())

    # Determine hedge direction (opposite of main direction)
    hedge_direction = "short" if direction == "long" else "long"

    # Build order that will pass all gates
    order = {
        "ticker": ticker,
        "direction": direction,
        "hedge_ticker": hedge_ticker,
        "hedge_direction": hedge_direction,
        "conviction": conviction,
        "risk_decision": risk_decision_dict,
        "execute": True,
        "size_pct_nav": size_pct_nav,
        "proposal_id": proposal_id,
        "order_id": f"order_{proposal_id}",
        "stop_loss_method": "trailing 2.5% from peak",
        "take_profit": "5% triggers review",
        "expected_holding_period": "60 days",
        "pm_rationale": pm_rationale,
        "_debates": debate_results,
        "_tech_score": tech_score,
    }

    # Run Phase 8 booking
    book = run_phase_8_single_order(order, tmp_dir)

    # Verify the order was booked (gates pass, no circuit breaker, price available)
    assert len(book["positions"]) == 1, (
        f"Expected 1 position to be booked but got {len(book['positions'])}"
    )

    # Find the auto_booked journal entry
    booked_entries = [
        j for j in book["trade_journal"] if j["action"] == "auto_booked"
    ]
    assert len(booked_entries) == 1, (
        f"Expected exactly 1 auto_booked journal entry, got {len(booked_entries)}. "
        f"Journal: {book['trade_journal']}"
    )

    journal_entry = booked_entries[0]

    # Core property: ALL required provenance fields must be present as keys
    for field in REQUIRED_PROVENANCE_FIELDS:
        assert field in journal_entry, (
            f"Provenance field '{field}' is MISSING from auto_booked journal entry. "
            f"Entry keys: {list(journal_entry.keys())}"
        )

    # Verify values match what was passed in
    assert journal_entry["proposal_id"] == proposal_id, (
        f"proposal_id mismatch: expected {proposal_id!r}, got {journal_entry['proposal_id']!r}"
    )
    assert journal_entry["pm_rationale"] == pm_rationale, (
        f"pm_rationale mismatch: expected {pm_rationale!r}, got {journal_entry['pm_rationale']!r}"
    )
    assert journal_entry["risk_decision"] == risk_decision_dict, (
        f"risk_decision mismatch: expected {risk_decision_dict!r}, got {journal_entry['risk_decision']!r}"
    )
    assert journal_entry["debate_results"] == debate_results, (
        f"debate_results mismatch: expected {debate_results!r}, got {journal_entry['debate_results']!r}"
    )
    assert journal_entry["tech_score"] == tech_score, (
        f"tech_score mismatch: expected {tech_score!r}, got {journal_entry['tech_score']!r}"
    )
