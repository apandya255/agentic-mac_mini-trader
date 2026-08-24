"""
Unit tests for run_cycle.py integration of structured logging,
atomic writes, and pipeline recovery.

Tests cover:
- Overlap guard prevents concurrent execution (exits 0)
- Atomic write produces valid JSON (no partial writes)
- Failure sends Telegram alert and exits with code 1

Requirements: 4.3, 4.4, 6.1, 6.2, 6.3, 6.4
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_cycle import atomic_write_book, _handle_pipeline_failure


class TestAtomicWriteBook:
    """Tests for atomic_write_book function."""

    def test_writes_valid_json(self, tmp_path):
        """Atomic write produces a valid JSON file."""
        book_path = tmp_path / "book.json"
        data = {"nav": 10_000_000, "positions": [{"ticker": "XOM", "direction": "long"}]}

        atomic_write_book(book_path, data)

        assert book_path.exists()
        loaded = json.loads(book_path.read_text())
        assert loaded == data

    def test_tmp_file_cleaned_up(self, tmp_path):
        """The .tmp file does not remain after atomic write completes."""
        book_path = tmp_path / "book.json"
        tmp_file = book_path.with_suffix('.tmp')
        data = {"nav": 5_000_000}

        atomic_write_book(book_path, data)

        assert not tmp_file.exists()
        assert book_path.exists()

    def test_overwrites_existing_file_atomically(self, tmp_path):
        """Atomic write replaces existing content completely."""
        book_path = tmp_path / "book.json"
        old_data = {"nav": 10_000_000, "positions": []}
        new_data = {"nav": 9_500_000, "positions": [{"ticker": "AAPL"}]}

        # Write initial state
        book_path.write_text(json.dumps(old_data))

        # Atomic overwrite
        atomic_write_book(book_path, new_data)

        loaded = json.loads(book_path.read_text())
        assert loaded == new_data
        assert loaded["nav"] == 9_500_000

    def test_preserves_original_on_no_write(self, tmp_path):
        """If atomic_write_book is never called, the original file is untouched."""
        book_path = tmp_path / "book.json"
        original = {"nav": 10_000_000, "status": "original"}
        book_path.write_text(json.dumps(original))

        # Don't call atomic_write_book — file should remain original
        loaded = json.loads(book_path.read_text())
        assert loaded == original

    def test_complex_nested_data(self, tmp_path):
        """Atomic write handles complex nested structures correctly."""
        book_path = tmp_path / "book.json"
        data = {
            "nav": 10_000_000,
            "positions": [
                {
                    "ticker": "XOM",
                    "direction": "long",
                    "entry_price": 112.45,
                    "trail_stop_level": 109.64,
                    "price_history": [112.0, 113.5, 114.2],
                }
            ],
            "trade_journal": [
                {"action": "auto_booked", "timestamp": "2025-07-15T09:40:00"}
            ],
        }

        atomic_write_book(book_path, data)

        loaded = json.loads(book_path.read_text())
        assert loaded["positions"][0]["ticker"] == "XOM"
        assert loaded["positions"][0]["trail_stop_level"] == 109.64


class TestOverlapGuardIntegration:
    """Tests for overlap guard preventing concurrent execution in run_cycle."""

    def test_overlap_raises_runtime_error(self, tmp_path):
        """Overlap guard raises RuntimeError('cycle_skipped_overlap') on contention."""
        from src.trading.overlap_guard import pipeline_lock

        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                # Attempt second lock — should raise
                with pytest.raises(RuntimeError, match="cycle_skipped_overlap"):
                    with pipeline_lock():
                        pass

    def test_overlap_exits_cleanly(self, tmp_path):
        """On overlap, the pipeline should log and not crash."""
        from src.trading.overlap_guard import pipeline_lock

        lock_file = tmp_path / "pipeline.lock"
        results = {"first_ran": False, "second_skipped": False}

        def first_lock():
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                with pipeline_lock():
                    results["first_ran"] = True
                    time.sleep(0.3)

        def second_lock():
            time.sleep(0.1)
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                try:
                    with pipeline_lock():
                        pass
                except RuntimeError as e:
                    if "cycle_skipped_overlap" in str(e):
                        results["second_skipped"] = True

        t1 = threading.Thread(target=first_lock)
        t2 = threading.Thread(target=second_lock)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results["first_ran"]
        assert results["second_skipped"]


class TestPipelineFailureRecovery:
    """Tests for pipeline failure handling (traceback logging + Telegram alert)."""

    def test_failure_logs_traceback(self, tmp_path):
        """On failure, a traceback file is written to memos/logs/."""
        mock_send = MagicMock(return_value=True)
        cycle_id = "2025-07-15T09:40:00"

        with patch("run_cycle.LOG_DIR", tmp_path), \
             patch("run_cycle.timestamp", return_value="2025-07-15T09-40-00"):
            try:
                raise ValueError("Test pipeline error")
            except ValueError as e:
                _handle_pipeline_failure(cycle_id, 12.5, "risk_gate", e, mock_send)

        # Check traceback file was written
        tb_files = list(tmp_path.glob("traceback_*.log"))
        assert len(tb_files) == 1
        content = tb_files[0].read_text()
        assert "ValueError" in content
        assert "Test pipeline error" in content

    def test_failure_sends_telegram_alert(self, tmp_path):
        """On failure, a Telegram alert is sent with cycle_id, phase, and error."""
        mock_send = MagicMock(return_value=True)
        cycle_id = "2025-07-15T09:40:00"

        with patch("run_cycle.LOG_DIR", tmp_path), \
             patch("run_cycle.timestamp", return_value="2025-07-15T09-40-00"):
            try:
                raise RuntimeError("Database connection lost")
            except RuntimeError as e:
                _handle_pipeline_failure(cycle_id, 45.2, "data_refresh", e, mock_send)

        # Verify Telegram was called with correct info
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        message = call_args[0][0]
        assert "2025-07-15T09:40:00" in message
        assert "data_refresh" in message
        assert "Database connection lost" in message
        assert call_args[1]["severity"] == "critical"

    def test_failure_handles_telegram_error_gracefully(self, tmp_path):
        """If Telegram alert fails, the pipeline failure handler doesn't crash."""
        mock_send = MagicMock(side_effect=Exception("Telegram API timeout"))
        cycle_id = "2025-07-15T09:40:00"

        with patch("run_cycle.LOG_DIR", tmp_path), \
             patch("run_cycle.timestamp", return_value="2025-07-15T09-40-00"):
            try:
                raise ValueError("Some error")
            except ValueError as e:
                # Should not raise even though Telegram fails
                _handle_pipeline_failure(cycle_id, 10.0, "proposals", e, mock_send)

        # Traceback file should still be written
        tb_files = list(tmp_path.glob("traceback_*.log"))
        assert len(tb_files) == 1

    def test_failure_calls_log_cycle_complete_with_exit_1(self, tmp_path):
        """On failure, log_cycle_complete is called with exit_code=1."""
        mock_send = MagicMock(return_value=True)
        cycle_id = "2025-07-15T09:40:00"

        with patch("run_cycle.LOG_DIR", tmp_path), \
             patch("run_cycle.timestamp", return_value="2025-07-15T09-40-00"), \
             patch("run_cycle.log_cycle_complete") as mock_log_complete, \
             patch("run_cycle.log_phase_complete"):
            try:
                raise ValueError("Error in phase")
            except ValueError as e:
                _handle_pipeline_failure(cycle_id, 30.0, "debate", e, mock_send)

        mock_log_complete.assert_called_once_with(
            cycle_id, 30.0, 0, 0, exit_code=1
        )
