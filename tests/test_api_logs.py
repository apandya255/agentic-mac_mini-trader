"""Unit tests for the /api/logs endpoint in serve.py.

Validates: Requirements 18.3
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def app_client(tmp_path):
    """Create a Flask test client with memos/logs/ pointing to a temp directory."""
    # Create temp structure
    logs_dir = tmp_path / "memos" / "logs"
    logs_dir.mkdir(parents=True)
    state_dir = tmp_path / "memos" / "state"
    state_dir.mkdir(parents=True)

    # Write a minimal book.json so the app can load
    book = {"nav": 10_000_000, "initial_nav": 10_000_000, "cash_pct": 1.0,
            "positions": [], "trade_journal": []}
    (state_dir / "book.json").write_text(json.dumps(book))

    # Patch LOGS_DIR in serve module
    import serve
    original_logs_dir = serve.LOGS_DIR
    serve.LOGS_DIR = logs_dir

    client = serve.app.test_client()
    yield client, logs_dir

    # Restore
    serve.LOGS_DIR = original_logs_dir


class TestApiLogs:
    """Tests for GET /api/logs endpoint."""

    def test_returns_empty_list_when_no_logs(self, app_client):
        """Returns empty array when memos/logs/ has no JSON files."""
        client, logs_dir = app_client
        resp = client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_returns_all_json_files(self, app_client):
        """Returns all JSON files from memos/logs/, not just cycle_* prefixed."""
        client, logs_dir = app_client

        # Write logs with different prefixes
        entries = [
            {"timestamp": "2025-07-01T10:00:00-04:00", "cycle_type": "price_poll",
             "status": "success", "duration_seconds": 5.0, "metrics": {}},
            {"timestamp": "2025-07-01T11:00:00-04:00", "cycle_type": "daily_sweep",
             "status": "success", "duration_seconds": 120.0, "metrics": {}},
            {"timestamp": "2025-07-01T12:00:00-04:00", "cycle_type": "full_desk_run",
             "status": "failure", "duration_seconds": 300.0, "metrics": {}, "error": "timeout"},
        ]
        (logs_dir / "price_poll_2025-07-01T10-00-00.json").write_text(json.dumps(entries[0]))
        (logs_dir / "daily_sweep_2025-07-01T11-00-00.json").write_text(json.dumps(entries[1]))
        (logs_dir / "full_desk_run_2025-07-01T12-00-00.json").write_text(json.dumps(entries[2]))

        resp = client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3

    def test_sorted_by_timestamp_descending(self, app_client):
        """Logs are returned sorted by timestamp descending (most recent first)."""
        client, logs_dir = app_client

        entries = [
            {"timestamp": "2025-07-01T09:00:00-04:00", "cycle_type": "price_poll",
             "status": "success", "duration_seconds": 5.0, "metrics": {}},
            {"timestamp": "2025-07-01T12:00:00-04:00", "cycle_type": "daily_sweep",
             "status": "success", "duration_seconds": 120.0, "metrics": {}},
            {"timestamp": "2025-07-01T10:30:00-04:00", "cycle_type": "price_poll",
             "status": "success", "duration_seconds": 4.5, "metrics": {}},
        ]
        (logs_dir / "price_poll_2025-07-01T09-00-00.json").write_text(json.dumps(entries[0]))
        (logs_dir / "daily_sweep_2025-07-01T12-00-00.json").write_text(json.dumps(entries[1]))
        (logs_dir / "price_poll_2025-07-01T10-30-00.json").write_text(json.dumps(entries[2]))

        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 3
        # Most recent first
        assert data[0]["timestamp"] == "2025-07-01T12:00:00-04:00"
        assert data[1]["timestamp"] == "2025-07-01T10:30:00-04:00"
        assert data[2]["timestamp"] == "2025-07-01T09:00:00-04:00"

    def test_skips_malformed_json_files(self, app_client):
        """Malformed JSON files are skipped gracefully."""
        client, logs_dir = app_client

        # Valid entry
        valid = {"timestamp": "2025-07-01T10:00:00-04:00", "cycle_type": "price_poll",
                 "status": "success", "duration_seconds": 5.0, "metrics": {}}
        (logs_dir / "price_poll_2025-07-01T10-00-00.json").write_text(json.dumps(valid))

        # Malformed file
        (logs_dir / "broken_2025-07-01T11-00-00.json").write_text("not valid json {{{")

        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["cycle_type"] == "price_poll"

    def test_includes_duration_and_status(self, app_client):
        """Each log entry includes duration_seconds and status fields."""
        client, logs_dir = app_client

        entry = {"timestamp": "2025-07-01T10:00:00-04:00", "cycle_type": "price_poll",
                 "trigger_source": "launchd", "status": "success",
                 "duration_seconds": 5.234, "metrics": {"tickers_updated": 50},
                 "error": None}
        (logs_dir / "price_poll_2025-07-01T10-00-00.json").write_text(json.dumps(entry))

        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["duration_seconds"] == 5.234
        assert data[0]["status"] == "success"
        assert data[0]["timestamp"] == "2025-07-01T10:00:00-04:00"
        assert data[0]["cycle_type"] == "price_poll"

    def test_nonexistent_logs_dir(self, app_client, tmp_path):
        """Returns empty array when logs directory doesn't exist."""
        client, _ = app_client
        import serve
        serve.LOGS_DIR = tmp_path / "nonexistent" / "logs"

        resp = client.get("/api/logs")
        data = resp.get_json()
        assert data == []

    def test_ignores_non_json_files(self, app_client):
        """Non-JSON files (e.g., .log files) are not included."""
        client, logs_dir = app_client

        # Valid JSON entry
        entry = {"timestamp": "2025-07-01T10:00:00-04:00", "cycle_type": "price_poll",
                 "status": "success", "duration_seconds": 5.0, "metrics": {}}
        (logs_dir / "price_poll_2025-07-01T10-00-00.json").write_text(json.dumps(entry))

        # Non-JSON files (stdout/stderr logs from launchd)
        (logs_dir / "poller_stdout.log").write_text("some stdout output")
        (logs_dir / "poller_stderr.log").write_text("some stderr output")

        resp = client.get("/api/logs")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["cycle_type"] == "price_poll"
