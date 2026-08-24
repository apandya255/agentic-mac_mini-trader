"""Unit tests for src/data_platform/service_logger.py

Validates: Requirements 12.4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.data_platform.service_logger import log_service_restart, RESTART_LOG


@pytest.fixture
def tmp_restart_log(tmp_path, monkeypatch):
    """Redirect RESTART_LOG to a temp file for testing."""
    log_path = tmp_path / "service_restarts.log"
    monkeypatch.setattr(
        "src.data_platform.service_logger.RESTART_LOG", log_path
    )
    return log_path


class TestLogServiceRestart:
    """Tests for the log_service_restart function."""

    def test_appends_to_file(self, tmp_restart_log):
        """log_service_restart appends a line to the log file."""
        log_service_restart("serve.py", exit_code=1, signal=None)

        assert tmp_restart_log.exists()
        content = tmp_restart_log.read_text()
        assert "serve.py" in content
        assert "restarted" in content

    def test_multiple_calls_accumulate_entries(self, tmp_restart_log):
        """Multiple calls accumulate entries in the log file."""
        log_service_restart("serve.py", exit_code=1, signal=None)
        log_service_restart("cloudflared", exit_code=137, signal="SIGKILL")
        log_service_restart("price_poller", exit_code=0, signal=None)

        content = tmp_restart_log.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3

    def test_file_created_if_absent(self, tmp_restart_log):
        """Log file is created if it does not exist."""
        assert not tmp_restart_log.exists()

        log_service_restart("serve.py", exit_code=1)

        assert tmp_restart_log.exists()

    def test_format_matches_expected_pattern(self, tmp_restart_log):
        """Log format matches: {timestamp} {service_name} restarted (previous exit code: {code}, signal: {signal})"""
        log_service_restart("serve.py", exit_code=1, signal="SIGTERM")

        content = tmp_restart_log.read_text().strip()
        # Expected pattern: ISO timestamp, service name, restarted text, exit code, signal
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00 serve\.py restarted \(previous exit code: 1, signal: SIGTERM\)$"
        assert re.match(pattern, content), f"Line did not match expected format: {content}"

    def test_unknown_exit_code_when_none(self, tmp_restart_log):
        """Exit code displays as 'unknown' when None is passed."""
        log_service_restart("cloudflared", exit_code=None, signal=None)

        content = tmp_restart_log.read_text()
        assert "previous exit code: unknown" in content

    def test_signal_none_when_not_provided(self, tmp_restart_log):
        """Signal displays as 'None' when not provided."""
        log_service_restart("serve.py", exit_code=0)

        content = tmp_restart_log.read_text()
        assert "signal: None" in content

    def test_signal_value_preserved(self, tmp_restart_log):
        """Signal value is preserved in the log entry."""
        log_service_restart("cloudflared", exit_code=137, signal="SIGKILL")

        content = tmp_restart_log.read_text()
        assert "signal: SIGKILL" in content

    def test_creates_parent_directory_if_absent(self, tmp_path, monkeypatch):
        """Parent directories are created if they don't exist."""
        nested_log = tmp_path / "nested" / "dir" / "service_restarts.log"
        monkeypatch.setattr(
            "src.data_platform.service_logger.RESTART_LOG", nested_log
        )

        log_service_restart("serve.py", exit_code=1)

        assert nested_log.exists()

    def test_timestamp_is_utc_iso_format(self, tmp_restart_log):
        """Timestamp is in UTC ISO format."""
        log_service_restart("serve.py", exit_code=0)

        content = tmp_restart_log.read_text()
        # Extract timestamp (everything before the first space after the ISO date)
        timestamp_str = content.split(" ")[0]
        assert "+00:00" in timestamp_str or "Z" in timestamp_str
