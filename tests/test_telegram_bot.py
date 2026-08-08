"""Unit tests for src/telegram_bot.py

Validates: Requirements 13.6, 13.8
- 13.6: Message splitting at 4000-char boundary (never truncates numbers)
- 13.8: Retry-once on delivery failure before marking failed
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.telegram_bot import split_message, send_message, _get_config


# ---------------------------------------------------------------------------
# Tests for split_message
# ---------------------------------------------------------------------------


class TestSplitMessage:
    """Tests for split_message — 4000-char boundary splitting on newlines."""

    def test_short_message_returns_single_chunk(self):
        """A message under 4000 chars comes back as a single-element list."""
        msg = "Trail breach: XOM closed at $112.45, P&L -2.7%"
        result = split_message(msg)
        assert result == [msg]

    def test_exactly_4000_chars_returns_single_chunk(self):
        """A message of exactly max_length stays as one chunk."""
        msg = "x" * 4000
        result = split_message(msg)
        assert result == [msg]

    def test_splits_on_newline_boundary(self):
        """Splitting happens at newline boundaries, never mid-line."""
        # Build a message with lines that force a split
        line = "A" * 100 + "\n"  # 101 chars per line (including newline)
        # 40 lines = 4040 chars — should trigger a split
        msg = line * 40
        result = split_message(msg.rstrip("\n"), max_length=4000)
        assert len(result) >= 2
        # Each chunk should not contain a truncated line
        for chunk in result:
            # Every line in the chunk should be complete
            lines = chunk.split("\n")
            for l in lines:
                assert len(l) == 100 or l == ""  # full lines only

    def test_never_truncates_numbers(self):
        """Lines with numeric data remain intact across the split."""
        lines = []
        for i in range(50):
            lines.append(f"Position {i}: P&L $1,234,567.89 ({i * 0.5:.2f}%)")
        msg = "\n".join(lines)
        result = split_message(msg, max_length=500)
        # Reassemble and verify no data loss
        reassembled = "\n".join(result)
        assert reassembled == msg

    def test_single_line_exceeding_max_gets_own_chunk(self):
        """A single line longer than max_length gets its own chunk (never truncated)."""
        long_line = "X" * 5000
        short_line = "Short line here"
        msg = f"{short_line}\n{long_line}\n{short_line}"
        result = split_message(msg, max_length=4000)
        # The long line must appear intact in one of the chunks
        assert any(long_line in chunk for chunk in result)

    def test_empty_message_returns_single_empty_chunk(self):
        """An empty string returns a list with one empty string."""
        result = split_message("")
        assert result == [""]

    def test_custom_max_length(self):
        """The max_length parameter is respected."""
        lines = ["Line " + str(i) for i in range(100)]
        msg = "\n".join(lines)
        result = split_message(msg, max_length=200)
        for chunk in result:
            # Chunks should be at or under 200 chars (except unavoidably long lines)
            if "\n" in chunk:
                assert len(chunk) <= 200 or chunk.count("\n") == 0

    def test_preserves_all_content(self):
        """No content is lost during splitting — reassembly matches original."""
        lines = [f"Data row {i}: value={i * 3.14159:.6f}" for i in range(100)]
        msg = "\n".join(lines)
        result = split_message(msg, max_length=500)
        reassembled = "\n".join(result)
        assert reassembled == msg


# ---------------------------------------------------------------------------
# Tests for _get_config
# ---------------------------------------------------------------------------


class TestGetConfig:
    """Tests for _get_config — env var configuration loading."""

    def test_returns_token_and_chat_id_when_set(self):
        """Correctly reads both env vars when present."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "123:ABC",
            "TELEGRAM_CHAT_ID": "-100999",
        }):
            token, chat_id = _get_config()
            assert token == "123:ABC"
            assert chat_id == "-100999"

    def test_raises_when_token_missing(self):
        """Raises RuntimeError if TELEGRAM_BOT_TOKEN is not set."""
        with patch.dict(os.environ, {
            "TELEGRAM_CHAT_ID": "-100999",
        }, clear=True):
            # Ensure token is not in env
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                _get_config()

    def test_raises_when_chat_id_missing(self):
        """Raises RuntimeError if TELEGRAM_CHAT_ID is not set."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "123:ABC",
        }, clear=True):
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            with pytest.raises(RuntimeError, match="TELEGRAM_CHAT_ID"):
                _get_config()

    def test_raises_when_both_missing(self):
        """Raises RuntimeError when neither env var is set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            with pytest.raises(RuntimeError):
                _get_config()

    def test_raises_when_token_is_empty_string(self):
        """Treats an empty string as missing."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "-100999",
        }):
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                _get_config()

    def test_raises_when_chat_id_is_empty_string(self):
        """Treats an empty string chat_id as missing."""
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "123:ABC",
            "TELEGRAM_CHAT_ID": "",
        }):
            with pytest.raises(RuntimeError, match="TELEGRAM_CHAT_ID"):
                _get_config()


# ---------------------------------------------------------------------------
# Tests for send_message — retry logic
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Tests for send_message — retry-once on failure, success paths."""

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_successful_send_returns_true(self, mock_config, mock_post, mock_log):
        """A single successful send returns True."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        result = send_message("Hello world")
        assert result is True
        mock_post.assert_called_once_with("token", "chat_id", "Hello world")

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_retry_on_first_failure_then_success(self, mock_config, mock_post, mock_log):
        """If first attempt fails and retry succeeds, returns True."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, True]  # fail then succeed
        with patch("src.telegram_bot.time.sleep"):
            result = send_message("Test retry")
        assert result is True
        assert mock_post.call_count == 2

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_retry_on_failure_both_attempts_fail(self, mock_config, mock_post, mock_log):
        """If both attempts fail, returns False."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, False]  # both fail
        with patch("src.telegram_bot.time.sleep"):
            result = send_message("Test double failure")
        assert result is False
        assert mock_post.call_count == 2

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_config_failure_returns_false(self, mock_config, mock_post, mock_log):
        """If _get_config raises RuntimeError, returns False without calling _post."""
        mock_config.side_effect = RuntimeError("TELEGRAM_BOT_TOKEN not set")
        result = send_message("No config")
        assert result is False
        mock_post.assert_not_called()

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_multi_chunk_all_succeed(self, mock_config, mock_post, mock_log):
        """A long message split into multiple chunks — all succeed, returns True."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        # Create a message that will definitely exceed 4000 chars (need many lines)
        lines = [f"Line {i:04d}: P&L=$1,234,567.89 delta=+0.45%" for i in range(150)]
        long_msg = "\n".join(lines)
        assert len(long_msg) > 4000  # sanity check
        result = send_message(long_msg)
        assert result is True
        assert mock_post.call_count > 1  # multiple chunks sent

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_multi_chunk_one_fails_after_retry(self, mock_config, mock_post, mock_log):
        """If one chunk in a multi-chunk message fails after retry, returns False."""
        mock_config.return_value = ("token", "chat_id")
        # First chunk succeeds, second chunk fails both attempts
        mock_post.side_effect = [True, False, False]
        # Create a message that will definitely split into 2+ chunks
        lines = [f"Line {i:04d}: P&L=$1,234,567.89 delta=+0.45%" for i in range(150)]
        long_msg = "\n".join(lines)
        assert len(long_msg) > 4000  # sanity check
        with patch("src.telegram_bot.time.sleep"):
            result = send_message(long_msg)
        assert result is False

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_logs_delivery_on_success(self, mock_config, mock_post, mock_log):
        """Successful delivery logs a 'success' entry."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.return_value = True
        send_message("Log test")
        mock_log.assert_called_once_with("success", "Log test", attempt=1)

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_logs_retry_then_success(self, mock_config, mock_post, mock_log):
        """Failed first attempt logs 'retry', then successful retry logs 'success'."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, True]
        with patch("src.telegram_bot.time.sleep"):
            send_message("Retry log test")
        # Should have logged: retry (attempt 1) then success (attempt 2)
        log_calls = mock_log.call_args_list
        assert len(log_calls) == 2
        assert log_calls[0][0][0] == "retry"  # first positional arg is status
        assert log_calls[1][0][0] == "success"

    @patch("src.telegram_bot._log_delivery")
    @patch("src.telegram_bot._post_message")
    @patch("src.telegram_bot._get_config")
    def test_logs_failure_after_retry_exhausted(self, mock_config, mock_post, mock_log):
        """Both attempts fail — logs retry then failure."""
        mock_config.return_value = ("token", "chat_id")
        mock_post.side_effect = [False, False]
        with patch("src.telegram_bot.time.sleep"):
            send_message("Both fail test")
        log_calls = mock_log.call_args_list
        assert len(log_calls) == 2
        assert log_calls[0][0][0] == "retry"
        assert log_calls[1][0][0] == "failure"
