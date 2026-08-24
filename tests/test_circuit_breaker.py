"""
Unit tests for src/trading/circuit_breaker.py

Tests the circuit breaker module which manages intraday drawdown detection
and session NAV reset functionality.

Requirements: 2.1, 2.2, 2.4, 5.1, 5.2, 5.3
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.circuit_breaker import (
    DRAWDOWN_THRESHOLD,
    CircuitBreakerState,
    _SESSION_NAV_SIDECAR,
    _load_session_nav_sidecar,
    _save_session_nav_sidecar,
    compute_intraday_drawdown,
    is_circuit_breaker_active,
    reset_session_nav,
)


class TestComputeIntradayDrawdown:
    """Tests for compute_intraday_drawdown."""

    def test_no_change(self):
        """Zero drawdown when NAV is unchanged."""
        assert compute_intraday_drawdown(650_000_000, 650_000_000) == 0.0

    def test_positive_return(self):
        """Positive fraction when NAV increases."""
        result = compute_intraday_drawdown(663_000_000, 650_000_000)
        assert result == pytest.approx(0.02, rel=1e-9)

    def test_negative_return(self):
        """Negative fraction when NAV decreases."""
        result = compute_intraday_drawdown(637_000_000, 650_000_000)
        assert result == pytest.approx(-0.02, rel=1e-9)

    def test_exactly_minus_two_percent(self):
        """Exactly -2% drawdown."""
        session_nav = 100.0
        current_nav = 98.0
        result = compute_intraday_drawdown(current_nav, session_nav)
        assert result == pytest.approx(-0.02, rel=1e-9)

    def test_session_open_nav_zero(self):
        """Returns 0.0 when session_open_nav is zero (edge case)."""
        assert compute_intraday_drawdown(100.0, 0.0) == 0.0

    def test_session_open_nav_negative(self):
        """Returns 0.0 when session_open_nav is negative (edge case)."""
        assert compute_intraday_drawdown(100.0, -50.0) == 0.0

    def test_large_drawdown(self):
        """Large drawdown is computed correctly."""
        result = compute_intraday_drawdown(50.0, 100.0)
        assert result == pytest.approx(-0.50, rel=1e-9)


class TestIsCircuitBreakerActive:
    """Tests for is_circuit_breaker_active."""

    def test_inactive_no_drawdown(self):
        """Circuit breaker inactive when NAV is unchanged."""
        state = is_circuit_breaker_active(650_000_000, 650_000_000)
        assert state.active is False
        assert state.current_drawdown == 0.0
        assert state.session_open_nav == 650_000_000

    def test_inactive_small_loss(self):
        """Circuit breaker inactive for a -1% loss (below threshold)."""
        session = 100.0
        current = 99.0  # -1%
        state = is_circuit_breaker_active(current, session)
        assert state.active is False
        assert state.current_drawdown == pytest.approx(-0.01, rel=1e-9)

    def test_active_at_threshold(self):
        """Circuit breaker active at exactly -2% drawdown."""
        session = 100.0
        current = 98.0  # exactly -2%
        state = is_circuit_breaker_active(current, session)
        assert state.active is True
        assert state.current_drawdown == pytest.approx(-0.02, rel=1e-9)

    def test_active_beyond_threshold(self):
        """Circuit breaker active for drawdown worse than -2%."""
        session = 100.0
        current = 95.0  # -5%
        state = is_circuit_breaker_active(current, session)
        assert state.active is True
        assert state.current_drawdown == pytest.approx(-0.05, rel=1e-9)

    def test_inactive_positive_return(self):
        """Circuit breaker inactive when portfolio is up."""
        session = 100.0
        current = 105.0  # +5%
        state = is_circuit_breaker_active(current, session)
        assert state.active is False
        assert state.current_drawdown == pytest.approx(0.05, rel=1e-9)

    def test_edge_case_session_nav_zero(self):
        """Circuit breaker inactive when session_open_nav is 0 (edge case guard)."""
        state = is_circuit_breaker_active(100.0, 0.0)
        assert state.active is False
        assert state.current_drawdown == 0.0

    def test_edge_case_session_nav_negative(self):
        """Circuit breaker inactive when session_open_nav is negative."""
        state = is_circuit_breaker_active(100.0, -10.0)
        assert state.active is False
        assert state.current_drawdown == 0.0

    def test_returns_dataclass(self):
        """Returns a proper CircuitBreakerState instance."""
        state = is_circuit_breaker_active(100.0, 100.0)
        assert isinstance(state, CircuitBreakerState)

    def test_just_above_threshold(self):
        """Circuit breaker inactive when drawdown is just above -2%."""
        session = 1000.0
        current = 980.01  # -1.999% — just above threshold
        state = is_circuit_breaker_active(current, session)
        assert state.active is False


class TestResetSessionNav:
    """Tests for reset_session_nav."""

    def test_records_session_nav(self):
        """Writes session_open_nav to book file."""
        book = {"nav": 650_000_000, "positions": [], "cash_pct": 0.5}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(json.dumps(book))
        tmp.close()

        try:
            result = reset_session_nav(Path(tmp.name))
            assert result == 650_000_000

            # Verify it was persisted
            updated_book = json.loads(Path(tmp.name).read_text())
            assert updated_book["session_open_nav"] == 650_000_000
        finally:
            os.unlink(tmp.name)

    def test_overwrites_existing_session_nav(self):
        """Overwrites a previously recorded session_open_nav."""
        book = {"nav": 700_000_000, "session_open_nav": 650_000_000, "positions": []}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(json.dumps(book))
        tmp.close()

        try:
            result = reset_session_nav(Path(tmp.name))
            assert result == 700_000_000

            updated_book = json.loads(Path(tmp.name).read_text())
            assert updated_book["session_open_nav"] == 700_000_000
        finally:
            os.unlink(tmp.name)

    def test_missing_nav_defaults_to_zero(self):
        """Defaults to 0 if nav key is missing from book."""
        book = {"positions": [], "cash_pct": 0.5}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(json.dumps(book))
        tmp.close()

        try:
            result = reset_session_nav(Path(tmp.name))
            assert result == 0

            updated_book = json.loads(Path(tmp.name).read_text())
            assert updated_book["session_open_nav"] == 0
        finally:
            os.unlink(tmp.name)

    def test_preserves_other_fields(self):
        """Does not alter other book fields."""
        book = {"nav": 100.0, "positions": [{"ticker": "AAPL"}], "cash_pct": 0.3}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(json.dumps(book))
        tmp.close()

        try:
            reset_session_nav(Path(tmp.name))
            updated_book = json.loads(Path(tmp.name).read_text())
            assert updated_book["positions"] == [{"ticker": "AAPL"}]
            assert updated_book["cash_pct"] == 0.3
            assert updated_book["nav"] == 100.0
        finally:
            os.unlink(tmp.name)

    def test_file_not_found(self):
        """FileNotFoundError triggers alert and returns sidecar value."""
        # Set up sidecar with a known value
        sidecar_dir = _SESSION_NAV_SIDECAR.parent
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        _SESSION_NAV_SIDECAR.write_text(json.dumps({"session_open_nav": 500_000}))

        try:
            with patch("src.telegram_bot.send_message") as mock_send:
                result = reset_session_nav(Path("/nonexistent/path/book.json"))
                assert result == 500_000
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert "FileNotFoundError" in call_args[0][0]
                assert call_args[1]["severity"] == "critical"
        finally:
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()

    def test_invalid_json(self):
        """JSONDecodeError triggers alert and returns sidecar value."""
        # Set up sidecar with a known value
        sidecar_dir = _SESSION_NAV_SIDECAR.parent
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        _SESSION_NAV_SIDECAR.write_text(json.dumps({"session_open_nav": 750_000}))

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write("not valid json {{{")
        tmp.close()

        try:
            with patch("src.telegram_bot.send_message") as mock_send:
                result = reset_session_nav(Path(tmp.name))
                assert result == 750_000
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert "JSONDecodeError" in call_args[0][0]
                assert call_args[1]["severity"] == "critical"
        finally:
            os.unlink(tmp.name)
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()

    def test_file_not_found_no_sidecar(self):
        """FileNotFoundError with no sidecar returns 0."""
        # Ensure sidecar does not exist
        if _SESSION_NAV_SIDECAR.exists():
            _SESSION_NAV_SIDECAR.unlink()

        with patch("src.telegram_bot.send_message"):
            result = reset_session_nav(Path("/nonexistent/path/book.json"))
            assert result == 0

    def test_sidecar_persistence_roundtrip(self):
        """Sidecar write and read produces same value."""
        sidecar_dir = _SESSION_NAV_SIDECAR.parent
        sidecar_dir.mkdir(parents=True, exist_ok=True)

        try:
            _save_session_nav_sidecar(123_456.78)
            result = _load_session_nav_sidecar()
            assert result == 123_456.78
        finally:
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()

    def test_sidecar_missing_returns_zero(self):
        """Missing sidecar file returns 0."""
        if _SESSION_NAV_SIDECAR.exists():
            _SESSION_NAV_SIDECAR.unlink()

        result = _load_session_nav_sidecar()
        assert result == 0

    def test_sidecar_corrupt_returns_zero(self):
        """Corrupt sidecar file returns 0."""
        sidecar_dir = _SESSION_NAV_SIDECAR.parent
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        _SESSION_NAV_SIDECAR.write_text("not valid json")

        try:
            result = _load_session_nav_sidecar()
            assert result == 0
        finally:
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()

    def test_successful_reset_persists_to_sidecar(self):
        """Successful reset also persists NAV to sidecar file."""
        book = {"nav": 900_000, "positions": []}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(json.dumps(book))
        tmp.close()

        try:
            result = reset_session_nav(Path(tmp.name))
            assert result == 900_000

            # Verify sidecar was written
            sidecar_data = json.loads(_SESSION_NAV_SIDECAR.read_text())
            assert sidecar_data["session_open_nav"] == 900_000
        finally:
            os.unlink(tmp.name)
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()

    def test_telegram_failure_does_not_crash(self):
        """Even if Telegram alert fails, function still returns sidecar value."""
        # Set up sidecar
        sidecar_dir = _SESSION_NAV_SIDECAR.parent
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        _SESSION_NAV_SIDECAR.write_text(json.dumps({"session_open_nav": 300_000}))

        try:
            with patch("src.telegram_bot.send_message", side_effect=Exception("network error")):
                result = reset_session_nav(Path("/nonexistent/path/book.json"))
                assert result == 300_000
        finally:
            if _SESSION_NAV_SIDECAR.exists():
                _SESSION_NAV_SIDECAR.unlink()
