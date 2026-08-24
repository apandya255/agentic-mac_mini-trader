"""Unit tests for the enhanced /api/alerts endpoint in serve.py.

Validates: Requirements 3.1, 3.2
Tests the merge of log-based alerts with monitor alerts from memos/state/alerts.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def app_client(tmp_path):
    """Create a Flask test client with memos dirs pointing to a temp directory."""
    # Create temp structure
    logs_dir = tmp_path / "memos" / "logs"
    logs_dir.mkdir(parents=True)
    state_dir = tmp_path / "memos" / "state"
    state_dir.mkdir(parents=True)

    # Write a minimal book.json so the app can load
    book = {"nav": 10_000_000, "initial_nav": 10_000_000, "cash_pct": 1.0,
            "positions": [], "trade_journal": []}
    (state_dir / "book.json").write_text(json.dumps(book))

    alerts_path = state_dir / "alerts.json"

    # Patch paths in serve module
    import serve
    original_logs_dir = serve.LOGS_DIR
    original_alerts_path = serve.ALERTS_PATH
    serve.LOGS_DIR = logs_dir
    serve.ALERTS_PATH = alerts_path

    client = serve.app.test_client()
    yield client, logs_dir, alerts_path

    # Restore
    serve.LOGS_DIR = original_logs_dir
    serve.ALERTS_PATH = original_alerts_path


class TestApiAlerts:
    """Tests for GET /api/alerts endpoint with monitor alerts merge."""

    def test_returns_all_three_fields(self, app_client):
        """Response contains alerts, monitor_alerts, and health fields."""
        client, logs_dir, alerts_path = app_client
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        assert "monitor_alerts" in data
        assert "health" in data

    def test_empty_when_no_data(self, app_client):
        """Returns empty lists when no log files and no alerts.json exist."""
        client, logs_dir, alerts_path = app_client
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["alerts"] == []
        assert data["monitor_alerts"] == []
        assert data["health"] == []

    def test_monitor_alerts_loaded_from_file(self, app_client):
        """Monitor alerts are loaded from memos/state/alerts.json when it exists."""
        client, logs_dir, alerts_path = app_client

        monitor_data = [
            {
                "level": "critical",
                "category": "stop",
                "ticker": "AAPL",
                "message": "Trail stop breached",
                "action": "Close position",
                "timestamp": "2025-07-01T10:00:00"
            },
            {
                "level": "warning",
                "category": "drawdown",
                "ticker": "PORTFOLIO",
                "message": "Drawdown at 3.2%",
                "action": "Monitor closely",
                "timestamp": "2025-07-01T10:05:00"
            }
        ]
        alerts_path.write_text(json.dumps(monitor_data))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert len(data["monitor_alerts"]) == 2
        assert data["monitor_alerts"][0]["level"] == "critical"
        assert data["monitor_alerts"][0]["ticker"] == "AAPL"
        assert data["monitor_alerts"][1]["category"] == "drawdown"

    def test_missing_alerts_file_returns_empty_monitor_alerts(self, app_client):
        """When alerts.json doesn't exist, monitor_alerts is an empty list."""
        client, logs_dir, alerts_path = app_client
        # Don't create the file
        assert not alerts_path.exists()

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert data["monitor_alerts"] == []

    def test_malformed_alerts_json_returns_empty_monitor_alerts(self, app_client):
        """When alerts.json contains invalid JSON, monitor_alerts is an empty list."""
        client, logs_dir, alerts_path = app_client
        alerts_path.write_text("not valid json {{{")

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert data["monitor_alerts"] == []

    def test_non_list_alerts_json_returns_empty_monitor_alerts(self, app_client):
        """When alerts.json contains a non-list value, monitor_alerts is an empty list."""
        client, logs_dir, alerts_path = app_client
        alerts_path.write_text(json.dumps({"not": "a list"}))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert data["monitor_alerts"] == []

    def test_log_based_alerts_still_returned(self, app_client):
        """Telegram delivery log entries are still returned as alerts."""
        client, logs_dir, alerts_path = app_client

        telegram_entry = {
            "timestamp": "2025-07-01T10:00:00-04:00",
            "cycle_type": "telegram_delivery",
            "message": "Trail stop breached for AAPL"
        }
        (logs_dir / "telegram_2025-07-01T10-00-00.json").write_text(json.dumps(telegram_entry))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["cycle_type"] == "telegram_delivery"

    def test_combined_response_has_both_alert_sources(self, app_client):
        """Response contains both log-based alerts and monitor alerts independently."""
        client, logs_dir, alerts_path = app_client

        # Log-based alert
        telegram_entry = {
            "timestamp": "2025-07-01T10:00:00-04:00",
            "cycle_type": "telegram_delivery",
            "message": "Trail stop breached for TSLA"
        }
        (logs_dir / "telegram_2025-07-01T10-00-00.json").write_text(json.dumps(telegram_entry))

        # Monitor alert
        monitor_data = [
            {
                "level": "info",
                "category": "sigma",
                "ticker": "NVDA",
                "message": "2-sigma event detected",
                "action": "Review position",
                "timestamp": "2025-07-01T11:00:00"
            }
        ]
        alerts_path.write_text(json.dumps(monitor_data))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["message"] == "Trail stop breached for TSLA"
        assert len(data["monitor_alerts"]) == 1
        assert data["monitor_alerts"][0]["ticker"] == "NVDA"
