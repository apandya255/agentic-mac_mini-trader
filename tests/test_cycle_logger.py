"""Unit tests for src/data_platform/cycle_logger.py

Validates: Requirements 14.1, 14.2, 14.3, 14.4, 18.1, 18.2, 18.5
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data_platform.cycle_logger import (
    log_cycle,
    log_cycle_start,
    log_phase_complete,
    log_cycle_complete,
    _get_cycle_log_path,
    LOGS_DIR,
)


class TestLogCycle:
    """Tests for the log_cycle function."""

    def _cleanup(self, path: Path):
        """Remove a test log file if it exists."""
        if path.exists():
            os.remove(path)

    def test_writes_json_file_to_logs_dir(self):
        """log_cycle writes a JSON file under memos/logs/."""
        path = log_cycle(
            cycle_type="price_poll",
            status="success",
            duration_seconds=5.2,
            metrics={"tickers_updated": 50},
            trigger_source="manual",
        )
        try:
            assert path.exists()
            assert path.parent == LOGS_DIR
            assert path.suffix == ".json"
            assert path.name.startswith("price_poll_")
        finally:
            self._cleanup(path)

    def test_schema_contains_all_required_fields(self):
        """Log entry has all fields defined in the design data model."""
        path = log_cycle(
            cycle_type="daily_sweep",
            status="failure",
            duration_seconds=30.0,
            metrics={"proposals_generated": 0, "orders_written": 0},
            error="API timeout",
            trigger_source="launchd",
        )
        try:
            with open(path) as f:
                data = json.load(f)

            required_fields = [
                "timestamp",
                "cycle_type",
                "trigger_source",
                "status",
                "duration_seconds",
                "metrics",
                "error",
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"
        finally:
            self._cleanup(path)

    def test_success_status_with_no_error(self):
        """Successful cycles have error=null."""
        path = log_cycle(
            cycle_type="full_desk_run",
            status="success",
            duration_seconds=120.5,
            metrics={"proposals_generated": 13, "orders_written": 6},
        )
        try:
            with open(path) as f:
                data = json.load(f)

            assert data["status"] == "success"
            assert data["error"] is None
            assert data["cycle_type"] == "full_desk_run"
            assert data["trigger_source"] == "launchd"  # default
        finally:
            self._cleanup(path)

    def test_failure_status_with_error_message(self):
        """Failed cycles capture the error string."""
        path = log_cycle(
            cycle_type="price_poll",
            status="failure",
            duration_seconds=0.5,
            metrics={},
            error="yfinance connection refused",
        )
        try:
            with open(path) as f:
                data = json.load(f)

            assert data["status"] == "failure"
            assert data["error"] == "yfinance connection refused"
        finally:
            self._cleanup(path)

    def test_skipped_status(self):
        """Skipped cycles log correctly."""
        path = log_cycle(
            cycle_type="daily_sweep",
            status="skipped",
            duration_seconds=0.01,
            metrics={},
        )
        try:
            with open(path) as f:
                data = json.load(f)

            assert data["status"] == "skipped"
            assert data["error"] is None
        finally:
            self._cleanup(path)

    def test_duration_rounded_to_3_decimals(self):
        """Duration is rounded to 3 decimal places."""
        path = log_cycle(
            cycle_type="price_poll",
            status="success",
            duration_seconds=12.123456789,
            metrics={},
        )
        try:
            with open(path) as f:
                data = json.load(f)

            assert data["duration_seconds"] == 12.123
        finally:
            self._cleanup(path)

    def test_metrics_dict_preserved(self):
        """Arbitrary metrics dict is preserved in the log."""
        metrics = {
            "tickers_updated": 145,
            "proposals_generated": 3,
            "orders_written": 1,
        }
        path = log_cycle(
            cycle_type="full_desk_run",
            status="success",
            duration_seconds=300.0,
            metrics=metrics,
        )
        try:
            with open(path) as f:
                data = json.load(f)

            assert data["metrics"] == metrics
        finally:
            self._cleanup(path)

    def test_timestamp_is_iso_format(self):
        """Timestamp field is a valid ISO 8601 string with timezone."""
        path = log_cycle(
            cycle_type="price_poll",
            status="success",
            duration_seconds=1.0,
            metrics={},
        )
        try:
            with open(path) as f:
                data = json.load(f)

            from datetime import datetime

            # Should parse without error
            parsed = datetime.fromisoformat(data["timestamp"])
            assert parsed.tzinfo is not None  # timezone-aware
        finally:
            self._cleanup(path)

    def test_filename_convention(self):
        """File naming follows {cycle_type}_{ISO_timestamp}.json pattern."""
        path = log_cycle(
            cycle_type="price_poll",
            status="success",
            duration_seconds=1.0,
            metrics={},
        )
        try:
            name = path.name
            assert name.startswith("price_poll_")
            assert name.endswith(".json")
            # Middle part should be a datetime-like string
            ts_part = name.replace("price_poll_", "").replace(".json", "")
            # Format: YYYY-MM-DDTHH-MM-SS
            assert len(ts_part) == 19
            assert ts_part[4] == "-"
            assert ts_part[10] == "T"
        finally:
            self._cleanup(path)

    def test_returns_path_object(self):
        """log_cycle returns a Path object."""
        path = log_cycle(
            cycle_type="price_poll",
            status="success",
            duration_seconds=1.0,
            metrics={},
        )
        try:
            assert isinstance(path, Path)
        finally:
            self._cleanup(path)



class TestPipelineCycleLogger:
    """Tests for pipeline-specific cycle logging (Requirements 14.1-14.4)."""

    def _cleanup_cycle(self, cycle_id: str):
        """Remove a test cycle log file if it exists."""
        path = _get_cycle_log_path(cycle_id)
        if path.exists():
            os.remove(path)

    def test_log_cycle_start_creates_file_and_returns_cycle_id(self):
        """log_cycle_start creates a JSON file and returns a valid cycle_id."""
        cycle_id = log_cycle_start(trigger_source="manual")
        try:
            assert cycle_id is not None
            # cycle_id should be an ISO timestamp format
            assert "T" in cycle_id
            assert len(cycle_id) == 19  # YYYY-MM-DDTHH:MM:SS

            # File should exist
            path = _get_cycle_log_path(cycle_id)
            assert path.exists()

            # File content should match expected structure
            with open(path) as f:
                data = json.load(f)
            assert data["cycle_id"] == cycle_id
            assert data["trigger_source"] == "manual"
            assert data["phases"] == []
            assert data["summary"] is None
        finally:
            self._cleanup_cycle(cycle_id)

    def test_log_cycle_start_default_trigger_source(self):
        """log_cycle_start defaults trigger_source to 'launchd'."""
        cycle_id = log_cycle_start()
        try:
            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)
            assert data["trigger_source"] == "launchd"
        finally:
            self._cleanup_cycle(cycle_id)

    def test_log_phase_complete_appends_phase(self):
        """log_phase_complete appends a phase entry to the phases array."""
        cycle_id = log_cycle_start(trigger_source="manual")
        try:
            log_phase_complete(cycle_id, "data_refresh", 12.345, "success")

            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)

            assert len(data["phases"]) == 1
            phase = data["phases"][0]
            assert phase["name"] == "data_refresh"
            assert phase["duration_s"] == 12.35  # rounded to 2 decimals
            assert phase["outcome"] == "success"
        finally:
            self._cleanup_cycle(cycle_id)

    def test_log_phase_complete_multiple_phases_accumulate(self):
        """Multiple log_phase_complete calls accumulate phases in order."""
        cycle_id = log_cycle_start(trigger_source="launchd")
        try:
            log_phase_complete(cycle_id, "data_refresh", 12.3, "success")
            log_phase_complete(cycle_id, "proposals", 45.1, "success")
            log_phase_complete(cycle_id, "debate", 90.2, "failure")

            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)

            assert len(data["phases"]) == 3
            assert data["phases"][0]["name"] == "data_refresh"
            assert data["phases"][1]["name"] == "proposals"
            assert data["phases"][2]["name"] == "debate"
            assert data["phases"][2]["outcome"] == "failure"
        finally:
            self._cleanup_cycle(cycle_id)

    def test_log_cycle_complete_adds_summary(self):
        """log_cycle_complete sets the summary object."""
        cycle_id = log_cycle_start(trigger_source="launchd")
        try:
            log_phase_complete(cycle_id, "data_refresh", 12.3, "success")
            log_cycle_complete(cycle_id, 193.1, proposals=4, trades=1, exit_code=0)

            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)

            assert data["summary"] is not None
            assert data["summary"]["total_duration_s"] == 193.1
            assert data["summary"]["proposals_generated"] == 4
            assert data["summary"]["trades_booked"] == 1
            assert data["summary"]["exit_code"] == 0
        finally:
            self._cleanup_cycle(cycle_id)

    def test_full_cycle_produces_expected_structure(self):
        """A complete cycle produces JSON matching the design data model."""
        cycle_id = log_cycle_start(trigger_source="launchd")
        try:
            log_phase_complete(cycle_id, "data_refresh", 12.3, "success")
            log_phase_complete(cycle_id, "proposals", 45.1, "success")
            log_phase_complete(cycle_id, "debate", 90.2, "success")
            log_phase_complete(cycle_id, "risk_gate", 30.5, "success")
            log_phase_complete(cycle_id, "pm_decision", 15.0, "success")
            log_cycle_complete(cycle_id, 193.1, proposals=4, trades=1, exit_code=0)

            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)

            # Top-level keys
            assert "cycle_id" in data
            assert "trigger_source" in data
            assert "phases" in data
            assert "summary" in data

            # Phases count
            assert len(data["phases"]) == 5

            # Each phase has required fields
            for phase in data["phases"]:
                assert "name" in phase
                assert "duration_s" in phase
                assert "outcome" in phase

            # Summary has required fields
            summary = data["summary"]
            assert "total_duration_s" in summary
            assert "proposals_generated" in summary
            assert "trades_booked" in summary
            assert "exit_code" in summary
        finally:
            self._cleanup_cycle(cycle_id)

    def test_log_phase_complete_with_missing_cycle_creates_entry(self):
        """log_phase_complete gracefully handles a missing cycle log."""
        # Use a fake cycle_id that was never started
        fake_cycle_id = "1999-01-01T00:00:00"
        try:
            log_phase_complete(fake_cycle_id, "data_refresh", 5.0, "success")

            path = _get_cycle_log_path(fake_cycle_id)
            assert path.exists()

            with open(path) as f:
                data = json.load(f)
            assert data["cycle_id"] == fake_cycle_id
            assert data["trigger_source"] == "unknown"
            assert len(data["phases"]) == 1
        finally:
            self._cleanup_cycle(fake_cycle_id)

    def test_log_cycle_complete_with_missing_cycle_creates_entry(self):
        """log_cycle_complete gracefully handles a missing cycle log."""
        fake_cycle_id = "1999-01-02T00:00:00"
        try:
            log_cycle_complete(fake_cycle_id, 50.0, proposals=2, trades=0, exit_code=1)

            path = _get_cycle_log_path(fake_cycle_id)
            assert path.exists()

            with open(path) as f:
                data = json.load(f)
            assert data["summary"]["exit_code"] == 1
            assert data["summary"]["proposals_generated"] == 2
        finally:
            self._cleanup_cycle(fake_cycle_id)

    def test_cycle_log_file_naming_convention(self):
        """Cycle log files follow cycle_{sanitized_timestamp}.json pattern."""
        cycle_id = log_cycle_start(trigger_source="manual")
        try:
            path = _get_cycle_log_path(cycle_id)
            assert path.name.startswith("cycle_")
            assert path.name.endswith(".json")
            # Should not contain colons (filesystem-unsafe)
            assert ":" not in path.name
        finally:
            self._cleanup_cycle(cycle_id)

    def test_duration_rounded_to_2_decimals(self):
        """Phase durations are rounded to 2 decimal places."""
        cycle_id = log_cycle_start()
        try:
            log_phase_complete(cycle_id, "test_phase", 12.3456789, "success")

            path = _get_cycle_log_path(cycle_id)
            with open(path) as f:
                data = json.load(f)

            assert data["phases"][0]["duration_s"] == 12.35
        finally:
            self._cleanup_cycle(cycle_id)
