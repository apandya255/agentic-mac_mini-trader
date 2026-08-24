"""
Unit tests for sigma event detection integrated in monitor.py.

Tests the check_sigma_events() function which detects outsized moves
on active positions and returns alerts + tickers for immediate re-evaluation.

Requirements: 6.1, 6.2, 6.3
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitor import check_sigma_events


def _make_position(ticker, daily_changes, status="active"):
    """Helper to build a position dict with price_history from daily changes."""
    price_history = [
        {"date": f"2025-06-{i+1:02d}", "price": 100 + i, "daily_change_pct": c}
        for i, c in enumerate(daily_changes)
    ]
    return {
        "ticker": ticker,
        "status": status,
        "direction": "long",
        "combined_pnl_pct": 0.02,
        "stop_loss_method": "trailing 2.5%",
        "take_profit": "5%",
        "trim_status": "untrimmed",
        "price_history": price_history,
    }


class TestCheckSigmaEvents:
    def test_no_active_positions(self):
        """Returns empty alerts and tickers when no positions are active."""
        book = {"positions": []}
        alerts, tickers = check_sigma_events(book)
        assert alerts == []
        assert tickers == []

    def test_position_with_insufficient_history(self):
        """Skips positions with fewer than 20 days of price_history."""
        changes = [0.01] * 15  # Only 15 days
        book = {"positions": [_make_position("AAPL", changes)]}
        alerts, tickers = check_sigma_events(book)
        assert alerts == []
        assert tickers == []

    def test_position_with_exactly_20_days_normal_move(self):
        """No sigma event when the latest move is within 2σ."""
        # 19 trailing days of small changes + 1 normal day today
        changes = [0.005, -0.005] * 10  # 20 entries, small variance
        book = {"positions": [_make_position("AAPL", changes)]}
        alerts, tickers = check_sigma_events(book)
        assert alerts == []
        assert tickers == []

    def test_position_triggers_sigma_event_large_move(self):
        """Triggers sigma event when latest move exceeds 2σ of trailing."""
        # 24 days of small normal moves, then a huge spike on day 25
        trailing = [0.005, -0.005, 0.003, -0.003, 0.004] * 5  # 25 normal days
        trailing.append(0.15)  # 15% move on the last day — massive sigma event
        book = {"positions": [_make_position("TSLA", trailing)]}
        alerts, tickers = check_sigma_events(book)
        assert len(alerts) == 1
        assert tickers == ["TSLA"]
        assert alerts[0].level == "critical"
        assert alerts[0].category == "sigma_event"
        assert alerts[0].ticker == "TSLA"
        assert "SIGMA EVENT" in alerts[0].message
        assert "0.15" in alerts[0].message or "15.00" in alerts[0].message

    def test_position_triggers_sigma_event_large_negative_move(self):
        """Triggers sigma event for large negative moves (symmetric detection)."""
        trailing = [0.005, -0.005, 0.003, -0.003, 0.004] * 5
        trailing.append(-0.12)  # -12% drop
        book = {"positions": [_make_position("GME", trailing)]}
        alerts, tickers = check_sigma_events(book)
        assert len(alerts) == 1
        assert tickers == ["GME"]
        assert alerts[0].level == "critical"
        assert alerts[0].category == "sigma_event"

    def test_closed_positions_are_skipped(self):
        """Closed positions are not checked for sigma events."""
        trailing = [0.005, -0.005] * 12
        trailing.append(0.20)  # Huge move, but position is closed
        pos = _make_position("XOM", trailing, status="closed")
        book = {"positions": [pos]}
        alerts, tickers = check_sigma_events(book)
        assert alerts == []
        assert tickers == []

    def test_multiple_positions_some_trigger(self):
        """Only positions with sigma events are reported."""
        # Position 1: normal move
        normal_changes = [0.005, -0.005] * 10 + [0.003]  # 21 days, normal last day
        # Position 2: sigma event
        sigma_changes = [0.005, -0.005] * 10 + [0.20]  # 21 days, huge last day

        book = {
            "positions": [
                _make_position("AAPL", normal_changes),
                _make_position("NVDA", sigma_changes),
            ]
        }
        alerts, tickers = check_sigma_events(book)
        assert len(alerts) == 1
        assert tickers == ["NVDA"]

    def test_alert_contains_magnitude_and_threshold(self):
        """Alert message includes the move magnitude and 2σ threshold."""
        trailing = [0.01, -0.01, 0.005, -0.005] * 6  # 24 days
        trailing.append(0.10)  # Spike
        book = {"positions": [_make_position("AMZN", trailing)]}
        alerts, tickers = check_sigma_events(book)
        assert len(alerts) == 1
        alert_dict = alerts[0].to_dict()
        assert alert_dict["level"] == "critical"
        assert alert_dict["category"] == "sigma_event"
        assert alert_dict["ticker"] == "AMZN"
        assert "threshold" in alert_dict["message"].lower() or "σ" in alert_dict["message"] or "2σ" in alert_dict["message"]

    def test_position_with_none_daily_changes(self):
        """Positions with None daily_change_pct values are handled gracefully."""
        price_history = [
            {"date": f"2025-06-{i+1:02d}", "price": 100, "daily_change_pct": None}
            for i in range(25)
        ]
        book = {
            "positions": [
                {
                    "ticker": "BAD",
                    "status": "active",
                    "price_history": price_history,
                }
            ]
        }
        alerts, tickers = check_sigma_events(book)
        # All None values filtered out → insufficient valid data
        assert alerts == []
        assert tickers == []

    def test_constant_price_history_no_event(self):
        """If all trailing changes are 0 (stddev=0), no sigma event is triggered."""
        # All zero changes → stddev = 0 → detect_sigma_event returns None
        changes = [0.0] * 20 + [0.05]  # stddev of trailing is 0
        book = {"positions": [_make_position("FLAT", changes)]}
        alerts, tickers = check_sigma_events(book)
        # stddev is 0 for trailing, so no event can trigger
        assert alerts == []
        assert tickers == []
