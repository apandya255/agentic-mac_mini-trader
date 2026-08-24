"""
Unit tests for progressive deleverage functionality in src/trading/circuit_breaker.py.

Tests the compute_progressive_deleverage function which returns None, 'deleverage',
or 'emergency' based on portfolio drawdown from session-open NAV.

Requirements: 15.1, 15.2, 15.3, 15.4
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.circuit_breaker import (
    DELEVERAGE_THRESHOLD,
    EMERGENCY_THRESHOLD,
    compute_progressive_deleverage,
)


class TestComputeProgressiveDeleverage:
    """Tests for compute_progressive_deleverage."""

    def test_returns_none_when_no_drawdown(self):
        """Returns None when portfolio has no loss."""
        result = compute_progressive_deleverage(100.0, 100.0)
        assert result is None

    def test_returns_none_when_positive_return(self):
        """Returns None when portfolio is up."""
        result = compute_progressive_deleverage(105.0, 100.0)
        assert result is None

    def test_returns_none_when_small_loss(self):
        """Returns None when drawdown is less than -3% (e.g., -1%)."""
        result = compute_progressive_deleverage(99.0, 100.0)
        assert result is None

    def test_returns_none_when_drawdown_between_two_and_three_percent(self):
        """Returns None when drawdown is between -2% and -3% (circuit breaker zone)."""
        result = compute_progressive_deleverage(97.5, 100.0)  # -2.5%
        assert result is None

    def test_returns_deleverage_at_exactly_minus_three_percent(self):
        """Returns 'deleverage' at exactly -3% drawdown (boundary)."""
        result = compute_progressive_deleverage(97.0, 100.0)
        assert result == "deleverage"

    def test_returns_deleverage_between_three_and_four_percent(self):
        """Returns 'deleverage' when -4% < drawdown <= -3%."""
        result = compute_progressive_deleverage(96.5, 100.0)  # -3.5%
        assert result == "deleverage"

    def test_returns_emergency_at_exactly_minus_four_percent(self):
        """Returns 'emergency' at exactly -4% drawdown (boundary)."""
        result = compute_progressive_deleverage(96.0, 100.0)
        assert result == "emergency"

    def test_returns_emergency_beyond_four_percent(self):
        """Returns 'emergency' when drawdown exceeds -4%."""
        result = compute_progressive_deleverage(90.0, 100.0)  # -10%
        assert result == "emergency"

    def test_returns_none_for_session_open_nav_zero(self):
        """Returns None when session_open_nav is zero (edge case guard)."""
        result = compute_progressive_deleverage(100.0, 0.0)
        assert result is None

    def test_returns_none_for_session_open_nav_negative(self):
        """Returns None when session_open_nav is negative (edge case guard)."""
        result = compute_progressive_deleverage(100.0, -50.0)
        assert result is None

    def test_boundary_just_above_deleverage(self):
        """Returns None when drawdown is just above -3% (e.g., -2.99%)."""
        session_nav = 10000.0
        current_nav = session_nav * (1 - 0.0299)  # -2.99%
        result = compute_progressive_deleverage(current_nav, session_nav)
        assert result is None

    def test_boundary_just_above_emergency(self):
        """Returns 'deleverage' when drawdown is just above -4% (e.g., -3.99%)."""
        session_nav = 10000.0
        current_nav = session_nav * (1 - 0.0399)  # -3.99%
        result = compute_progressive_deleverage(current_nav, session_nav)
        assert result == "deleverage"

    def test_large_nav_values(self):
        """Works correctly with large NAV values (real portfolio scale)."""
        session_nav = 650_000_000.0
        current_nav = session_nav * 0.965  # -3.5%
        result = compute_progressive_deleverage(current_nav, session_nav)
        assert result == "deleverage"

    def test_large_nav_emergency(self):
        """Works correctly with large NAV values at emergency threshold."""
        session_nav = 650_000_000.0
        current_nav = session_nav * 0.95  # -5%
        result = compute_progressive_deleverage(current_nav, session_nav)
        assert result == "emergency"


class TestDeleverageConstants:
    """Tests for deleverage threshold constants."""

    def test_deleverage_threshold_value(self):
        """DELEVERAGE_THRESHOLD is -0.03."""
        assert DELEVERAGE_THRESHOLD == -0.03

    def test_emergency_threshold_value(self):
        """EMERGENCY_THRESHOLD is -0.04."""
        assert EMERGENCY_THRESHOLD == -0.04

    def test_thresholds_ordering(self):
        """Emergency threshold is more severe (lower) than deleverage threshold."""
        assert EMERGENCY_THRESHOLD < DELEVERAGE_THRESHOLD
