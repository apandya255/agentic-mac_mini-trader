"""
Unit tests for Phase 8 autonomous auto-booking logic in run_cycle.py.

Validates:
- Gate validation integration (conviction, risk, pm_execute)
- Circuit breaker integration
- Slippage-adjusted fill pricing
- Cash accounting (2x size for pair trades)
- Provenance logging to trade journal
- Rejection logging with specific failing gate
- New position field initialization (trim_status, trail_stop_level, thesis_status)
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def make_order(
    ticker="XOM",
    direction="long",
    hedge_ticker="XLE",
    hedge_direction="short",
    conviction=8,
    risk_decision=None,
    execute=True,
    size_pct_nav=0.03,
    proposal_id="test_proposal_001",
):
    """Create a test order dict."""
    if risk_decision is None:
        risk_decision = {"decision": "approved", "rationale": "all clear"}
    return {
        "ticker": ticker,
        "direction": direction,
        "hedge_ticker": hedge_ticker,
        "hedge_direction": hedge_direction,
        "conviction": conviction,
        "risk_decision": risk_decision,
        "execute": execute,
        "size_pct_nav": size_pct_nav,
        "proposal_id": proposal_id,
        "order_id": f"order_{proposal_id}",
        "stop_loss_method": "trailing 2.5% from peak",
        "take_profit": "5% triggers review",
        "expected_holding_period": "60 days",
        "pm_rationale": "Strong conviction pair trade",
        "_tech_score": {"technical_score": 7},
        "_debates": [{"stance": "support"}],
    }


@pytest.fixture
def temp_state(tmp_path):
    """Set up temporary state directory with a book.json."""
    state_dir = tmp_path / "memos" / "state"
    state_dir.mkdir(parents=True)
    orders_dir = tmp_path / "memos" / "orders"
    orders_dir.mkdir(parents=True)
    logs_dir = tmp_path / "memos" / "logs"
    logs_dir.mkdir(parents=True)
    proposals_dir = tmp_path / "memos" / "proposals"
    proposals_dir.mkdir(parents=True)

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
    return tmp_path, book_path


class TestPhase8AutoBooking:
    """Tests for the autonomous Phase 8 booking logic."""

    def _run_phase_8(self, orders, book_path, tmp_path):
        """Run phase_8_update_book with patched paths and price service."""
        import run_cycle

        # Mock the price service to return known prices
        mock_price_service = MagicMock()
        mock_price_service.get_latest_close.side_effect = lambda t: {
            "XOM": 105.50,
            "XLE": 88.20,
            "CVX": 155.30,
            "RSPG": 72.10,
        }.get(t, None)

        mock_price_service_class = MagicMock(return_value=mock_price_service)

        with patch.object(run_cycle, "STATE_FILE", book_path), \
             patch.object(run_cycle, "MEMOS_DIR", tmp_path / "memos"), \
             patch.object(run_cycle, "LOG_DIR", tmp_path / "memos" / "logs"), \
             patch("data_platform.prices.PriceService", mock_price_service_class):
            run_cycle.phase_8_update_book(orders)

        return json.loads(book_path.read_text())

    def test_successful_booking(self, temp_state):
        """An order that passes all gates is booked with slippage-adjusted price."""
        tmp_path, book_path = temp_state
        order = make_order()
        book = self._run_phase_8([order], book_path, tmp_path)

        # Position should be added
        assert len(book["positions"]) == 1
        pos = book["positions"][0]
        assert pos["ticker"] == "XOM"
        assert pos["direction"] == "long"
        assert pos["status"] == "active"

        # Slippage-adjusted entry (long entry → price goes UP)
        # 105.50 * (1 + 5/10000) = 105.50 * 1.0005 = 105.55275
        assert pos["entry_price"] == pytest.approx(105.50 * 1.0005, rel=1e-6)

        # Hedge slippage-adjusted entry (short entry → price goes DOWN)
        # 88.20 * (1 - 5/10000) = 88.20 * 0.9995 = 88.1559
        assert pos["hedge_entry_price"] == pytest.approx(88.20 * 0.9995, rel=1e-6)

    def test_cash_reduced_by_2x_size(self, temp_state):
        """Cash is reduced by 2x size_pct_nav (both legs of pair)."""
        tmp_path, book_path = temp_state
        order = make_order(size_pct_nav=0.03)
        book = self._run_phase_8([order], book_path, tmp_path)

        # Original cash = 1.0, reduced by 2 * 0.03 = 0.06
        assert book["cash_pct"] == pytest.approx(1.0 - 0.06, rel=1e-9)

    def test_gate_rejection_conviction(self, temp_state):
        """Order rejected when conviction < 5."""
        tmp_path, book_path = temp_state
        order = make_order(conviction=3)
        book = self._run_phase_8([order], book_path, tmp_path)

        assert len(book["positions"]) == 0
        assert len(book["trade_journal"]) == 1
        assert book["trade_journal"][0]["action"] == "auto_rejected"
        assert book["trade_journal"][0]["failing_gate"] == "conviction"

    def test_gate_rejection_risk(self, temp_state):
        """Order rejected when risk decision is not approved."""
        tmp_path, book_path = temp_state
        order = make_order(risk_decision={"decision": "rejected", "rationale": "too risky"})
        book = self._run_phase_8([order], book_path, tmp_path)

        assert len(book["positions"]) == 0
        assert book["trade_journal"][0]["action"] == "auto_rejected"
        assert book["trade_journal"][0]["failing_gate"] == "risk"

    def test_gate_rejection_pm_execute(self, temp_state):
        """Order rejected when PM execute is False."""
        tmp_path, book_path = temp_state
        order = make_order(execute=False)
        book = self._run_phase_8([order], book_path, tmp_path)

        assert len(book["positions"]) == 0
        assert book["trade_journal"][0]["action"] == "auto_rejected"
        assert book["trade_journal"][0]["failing_gate"] == "pm_execute"

    def test_circuit_breaker_holds_order(self, temp_state):
        """Orders are held when circuit breaker is active."""
        tmp_path, book_path = temp_state

        # Set NAV to trigger circuit breaker (-3% drawdown from session open)
        book = json.loads(book_path.read_text())
        book["nav"] = 9_700_000  # 3% below session_open_nav of 10M
        book["session_open_nav"] = 10_000_000
        book_path.write_text(json.dumps(book, indent=2))

        order = make_order()
        book = self._run_phase_8([order], book_path, tmp_path)

        # Position should NOT be added
        assert len(book["positions"]) == 0
        # Journal should show circuit_breaker_held
        assert any(j["action"] == "circuit_breaker_held" for j in book["trade_journal"])
        # Held order persisted to file
        held_files = list((tmp_path / "memos" / "orders").glob("*_held.json"))
        assert len(held_files) == 1

    def test_provenance_logged(self, temp_state):
        """Booked positions log full provenance to trade journal."""
        tmp_path, book_path = temp_state
        order = make_order()
        book = self._run_phase_8([order], book_path, tmp_path)

        journal_entry = next(
            j for j in book["trade_journal"] if j["action"] == "auto_booked"
        )
        assert journal_entry["proposal_id"] == "test_proposal_001"
        assert journal_entry["debate_results"] is not None
        assert journal_entry["tech_score"] is not None
        assert journal_entry["risk_decision"] is not None
        assert journal_entry["pm_rationale"] is not None
        assert "timestamp" in journal_entry

    def test_new_position_fields_initialized(self, temp_state):
        """New positions have trim_status, trail_stop_level, thesis_status initialized."""
        tmp_path, book_path = temp_state
        order = make_order()
        book = self._run_phase_8([order], book_path, tmp_path)

        pos = book["positions"][0]
        assert pos["trim_status"] == "untrimmed"
        assert pos["trail_stop_level"] is None
        assert pos["thesis_status"] == "active"

    def test_missing_price_data_skips_order(self, temp_state):
        """Orders for tickers without price data are rejected."""
        tmp_path, book_path = temp_state
        order = make_order(ticker="UNKNOWN_TICKER")
        book = self._run_phase_8([order], book_path, tmp_path)

        assert len(book["positions"]) == 0
        assert book["trade_journal"][0]["failing_gate"] == "price_unavailable"

    def test_multiple_orders_independent(self, temp_state):
        """Multiple orders are processed independently."""
        tmp_path, book_path = temp_state
        orders = [
            make_order(ticker="XOM", proposal_id="p1", size_pct_nav=0.02),
            make_order(ticker="CVX", hedge_ticker="RSPG", proposal_id="p2", size_pct_nav=0.03),
        ]
        book = self._run_phase_8(orders, book_path, tmp_path)

        assert len(book["positions"]) == 2
        # Cash reduced by both: 2*0.02 + 2*0.03 = 0.10
        assert book["cash_pct"] == pytest.approx(1.0 - 0.10, rel=1e-9)
