"""
Unit tests for src/trading/slippage.py

Validates Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.slippage import get_slippage_bps, compute_fill_price


# ---------------------------------------------------------------------------
# get_slippage_bps tests
# ---------------------------------------------------------------------------


class TestGetSlippageBps:
    def test_default_value(self, monkeypatch):
        """Returns 5 when SLIPPAGE_BPS is not set."""
        monkeypatch.delenv("SLIPPAGE_BPS", raising=False)
        assert get_slippage_bps() == 5

    def test_reads_env_variable(self, monkeypatch):
        """Reads the integer value from SLIPPAGE_BPS."""
        monkeypatch.setenv("SLIPPAGE_BPS", "10")
        assert get_slippage_bps() == 10

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        """Falls back to 5 if SLIPPAGE_BPS is non-integer."""
        monkeypatch.setenv("SLIPPAGE_BPS", "abc")
        assert get_slippage_bps() == 5

    def test_zero_slippage(self, monkeypatch):
        """Supports zero slippage."""
        monkeypatch.setenv("SLIPPAGE_BPS", "0")
        assert get_slippage_bps() == 0


# ---------------------------------------------------------------------------
# compute_fill_price tests
# ---------------------------------------------------------------------------


class TestComputeFillPrice:
    def test_long_entry_price_increases(self):
        """Long entry: price × (1 + bps/10000) — Requirement 9.2"""
        price = 100.0
        result = compute_fill_price(price, "long", "entry", slippage_bps=5)
        assert result == pytest.approx(100.05)

    def test_short_entry_price_decreases(self):
        """Short entry: price × (1 - bps/10000) — Requirement 9.3"""
        price = 100.0
        result = compute_fill_price(price, "short", "entry", slippage_bps=5)
        assert result == pytest.approx(99.95)

    def test_long_exit_price_decreases(self):
        """Long exit: price × (1 - bps/10000) — Requirement 9.4"""
        price = 100.0
        result = compute_fill_price(price, "long", "exit", slippage_bps=5)
        assert result == pytest.approx(99.95)

    def test_short_exit_price_increases(self):
        """Short exit: price × (1 + bps/10000) — Requirement 9.5"""
        price = 100.0
        result = compute_fill_price(price, "short", "exit", slippage_bps=5)
        assert result == pytest.approx(100.05)

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError — Requirement 9.6"""
        with pytest.raises(ValueError, match="Invalid direction/side"):
            compute_fill_price(100.0, "neutral", "entry", slippage_bps=5)

    def test_invalid_side_raises(self):
        """Invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction/side"):
            compute_fill_price(100.0, "long", "hold", slippage_bps=5)

    def test_invalid_both_raises(self):
        """Invalid direction and side raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction/side"):
            compute_fill_price(100.0, "flat", "none", slippage_bps=5)

    def test_uses_env_default_when_bps_not_provided(self, monkeypatch):
        """When slippage_bps is None, reads from SLIPPAGE_BPS env."""
        monkeypatch.setenv("SLIPPAGE_BPS", "10")
        result = compute_fill_price(100.0, "long", "entry")
        # 10 bps = 0.001 factor → 100 × 1.001 = 100.1
        assert result == pytest.approx(100.10)

    def test_zero_slippage_returns_same_price(self):
        """With zero slippage, fill price equals observed price."""
        price = 150.0
        assert compute_fill_price(price, "long", "entry", slippage_bps=0) == price
        assert compute_fill_price(price, "short", "entry", slippage_bps=0) == price
        assert compute_fill_price(price, "long", "exit", slippage_bps=0) == price
        assert compute_fill_price(price, "short", "exit", slippage_bps=0) == price

    def test_larger_slippage(self):
        """Verifies calculation with 20 bps."""
        price = 200.0
        # 20 bps = 0.002
        assert compute_fill_price(price, "long", "entry", slippage_bps=20) == pytest.approx(200.40)
        assert compute_fill_price(price, "short", "entry", slippage_bps=20) == pytest.approx(199.60)
        assert compute_fill_price(price, "long", "exit", slippage_bps=20) == pytest.approx(199.60)
        assert compute_fill_price(price, "short", "exit", slippage_bps=20) == pytest.approx(200.40)
