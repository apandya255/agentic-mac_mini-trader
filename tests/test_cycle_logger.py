"""Unit tests for src/data_platform/cycle_logger.py

Validates: Requirements 18.1, 18.2, 18.5
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.data_platform.cycle_logger import log_cycle, LOGS_DIR


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
