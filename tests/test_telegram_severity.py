"""Unit tests for telegram_bot.py severity prefix and undelivered persistence.

Validates: Requirements 13.1, 13.2, 13.3, 13.4
- 13.1: Critical alert delivery within 30 seconds
- 13.2: Retry once after 1-second delay before marking failed
- 13.3: Persist undelivered messages to memos/logs/undelivered_alerts.json
- 13.4: Prefix messages with CRITICAL:/WARNING:/INFO: based on severity
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.telegram_bot import send_message, _persist_undelivered


# ---------------------------------------------------------------------------
# Tests for severity prefix
# ---------------------------------------------------------------------------


class TestSeverityPrefix:
    """Tests for severity prefix logic in send_message()."""

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_critical_prefix_applied(self, mock_config, mock_post, mock_log):
        """severity='critical' prefixes message with 'CRITICAL:'."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Stop breached on XOM", severity="critical")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("CRITICAL:")
        assert "Stop breached on XOM" in sent_text

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_warning_prefix_applied(self, mock_config, mock_post, mock_log):
        """severity='warning' prefixes message with 'WARNING:'."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Factor beta elevated", severity="warning")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("WARNING:")
        assert "Factor beta elevated" in sent_text

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_info_prefix_applied(self, mock_config, mock_post, mock_log):
        """severity='info' prefixes message with 'INFO:'."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Cycle completed successfully", severity="info")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("INFO:")
        assert "Cycle completed successfully" in sent_text

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_default_severity_is_info(self, mock_config, mock_post, mock_log):
        """Default severity (no param) uses 'INFO:' prefix."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Default severity test")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("INFO:")

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_prefix_not_duplicated_if_already_present(self, mock_config, mock_post, mock_log):
        """If message already starts with the correct prefix, don't double it."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("CRITICAL: Already prefixed", severity="critical")
        sent_text = mock_post.call_args[0][2]
        assert sent_text == "CRITICAL: Already prefixed"
        assert not sent_text.startswith("CRITICAL: CRITICAL:")

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_severity_case_insensitive(self, mock_config, mock_post, mock_log):
        """Severity parameter is case-insensitive."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Case test", severity="Critical")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("CRITICAL:")

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_unknown_severity_defaults_to_info(self, mock_config, mock_post, mock_log):
        """Unknown severity value falls back to INFO: prefix."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Unknown severity", severity="debug")
        sent_text = mock_post.call_args[0][2]
        assert sent_text.startswith("INFO:")


# ---------------------------------------------------------------------------
# Tests for _persist_undelivered
# ---------------------------------------------------------------------------


class TestPersistUndelivered:
    """Tests for _persist_undelivered — writing failed messages to JSON."""

    def test_creates_file_if_not_exists(self, tmp_path):
        """Creates undelivered_alerts.json if it doesn't exist."""
        with patch("src.telegram_bot.LOGS_DIR", tmp_path):
            _persist_undelivered("Test message", "critical", "Timeout")
            undelivered_path = tmp_path / "undelivered_alerts.json"
            assert undelivered_path.exists()
            entries = json.loads(undelivered_path.read_text())
            assert len(entries) == 1
            assert entries[0]["message"] == "Test message"
            assert entries[0]["severity"] == "critical"
            assert entries[0]["error"] == "Timeout"
            assert entries[0]["delivered"] is False
            assert "timestamp" in entries[0]

    def test_appends_to_existing_file(self, tmp_path):
        """Appends to existing entries without overwriting."""
        with patch("src.telegram_bot.LOGS_DIR", tmp_path):
            undelivered_path = tmp_path / "undelivered_alerts.json"
            # Pre-populate with one entry
            existing = [{"timestamp": "2025-01-01T00:00:00Z", "severity": "warning",
                         "message": "Old msg", "error": "Error", "delivered": False}]
            undelivered_path.write_text(json.dumps(existing))

            _persist_undelivered("New message", "critical", "API down")
            entries = json.loads(undelivered_path.read_text())
            assert len(entries) == 2
            assert entries[0]["message"] == "Old msg"
            assert entries[1]["message"] == "New message"
            assert entries[1]["severity"] == "critical"

    def test_handles_corrupt_existing_file(self, tmp_path):
        """If existing file has invalid JSON, starts fresh with new entry."""
        with patch("src.telegram_bot.LOGS_DIR", tmp_path):
            undelivered_path = tmp_path / "undelivered_alerts.json"
            undelivered_path.write_text("not valid json {{{")

            _persist_undelivered("Recovery msg", "warning", "Parse error")
            entries = json.loads(undelivered_path.read_text())
            assert len(entries) == 1
            assert entries[0]["message"] == "Recovery msg"

    def test_severity_stored_lowercase(self, tmp_path):
        """Severity is always stored in lowercase."""
        with patch("src.telegram_bot.LOGS_DIR", tmp_path):
            _persist_undelivered("Test", "CRITICAL", "err")
            entries = json.loads((tmp_path / "undelivered_alerts.json").read_text())
            assert entries[0]["severity"] == "critical"

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories if they don't exist."""
        nested_dir = tmp_path / "deep" / "nested" / "logs"
        with patch("src.telegram_bot.LOGS_DIR", nested_dir):
            _persist_undelivered("Deep msg", "info", "err")
            assert (nested_dir / "undelivered_alerts.json").exists()


# ---------------------------------------------------------------------------
# Tests for delivery failure persistence integration
# ---------------------------------------------------------------------------


class TestDeliveryFailurePersistence:
    """Tests verifying undelivered messages are persisted on delivery failure."""

    @patch("src.telegram_bot._persist_undelivered")
    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_persists_on_retry_failure(self, mock_config, mock_post, mock_log, mock_persist):
        """When delivery fails after retry, message is persisted."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, False]  # both attempts fail
        with patch("src.telegram_bot.time.sleep"):
            result = send_message("Critical alert", severity="critical")
        assert result is False
        mock_persist.assert_called_once()
        call_args = mock_persist.call_args[0]
        assert "Critical alert" in call_args[0]
        assert call_args[1] == "critical"
        assert call_args[2] == "Retry also failed"

    @patch("src.telegram_bot._persist_undelivered")
    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_no_persistence_on_success(self, mock_config, mock_post, mock_log, mock_persist):
        """When delivery succeeds, nothing is persisted."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        result = send_message("Good message", severity="info")
        assert result is True
        mock_persist.assert_not_called()

    @patch("src.telegram_bot._persist_undelivered")
    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_persists_on_config_failure(self, mock_config, mock_post, mock_log, mock_persist):
        """When config is missing, message is persisted as undelivered."""
        mock_config.side_effect = RuntimeError("TELEGRAM_BOT_TOKEN not set")
        result = send_message("No token msg", severity="warning")
        assert result is False
        mock_persist.assert_called_once()
        call_args = mock_persist.call_args[0]
        assert "No token msg" in call_args[0]
        assert call_args[1] == "warning"

    @patch("src.telegram_bot._persist_undelivered")
    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_no_persistence_on_retry_success(self, mock_config, mock_post, mock_log, mock_persist):
        """When first attempt fails but retry succeeds, nothing is persisted."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, True]  # fail then succeed
        with patch("src.telegram_bot.time.sleep"):
            result = send_message("Retry success", severity="info")
        assert result is True
        mock_persist.assert_not_called()
