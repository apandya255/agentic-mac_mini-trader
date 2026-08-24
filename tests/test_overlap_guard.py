"""
Unit tests for src/trading/overlap_guard.py

Tests the pipeline overlap guard which prevents concurrent pipeline executions
using an exclusive file lock (fcntl.flock).

Requirements: 7.5
"""

import fcntl
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.overlap_guard import LOCK_PATH, pipeline_lock


class TestPipelineLock:
    """Tests for the pipeline_lock context manager."""

    def test_acquires_and_releases_lock(self, tmp_path):
        """Lock can be acquired and released cleanly."""
        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                # Lock is held — lock file should exist with PID
                assert lock_file.exists()
                content = lock_file.read_text()
                assert content == str(os.getpid())

    def test_writes_pid_to_lock_file(self, tmp_path):
        """PID is written to the lock file while lock is held."""
        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                pid_in_file = int(lock_file.read_text())
                assert pid_in_file == os.getpid()

    def test_raises_runtime_error_on_overlap(self, tmp_path):
        """Raises RuntimeError('cycle_skipped_overlap') when lock is already held."""
        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                # Attempt to acquire the same lock again
                with pytest.raises(RuntimeError, match="cycle_skipped_overlap"):
                    with pipeline_lock():
                        pass  # pragma: no cover

    def test_lock_released_after_context_exit(self, tmp_path):
        """Lock is released after the context manager exits, allowing re-acquisition."""
        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                pass  # Lock held then released

            # Should be able to acquire again
            with pipeline_lock():
                assert lock_file.read_text() == str(os.getpid())

    def test_lock_released_on_exception(self, tmp_path):
        """Lock is released even if an exception occurs inside the context."""
        lock_file = tmp_path / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pytest.raises(ValueError, match="test error"):
                with pipeline_lock():
                    raise ValueError("test error")

            # Lock should be released — can re-acquire
            with pipeline_lock():
                assert lock_file.exists()

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories for the lock file if they don't exist."""
        lock_file = tmp_path / "nested" / "dir" / "pipeline.lock"
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                assert lock_file.exists()

    def test_concurrent_threads_mutual_exclusion(self, tmp_path):
        """Only one thread can hold the lock at a time; others get RuntimeError."""
        lock_file = tmp_path / "pipeline.lock"
        results = {"held": False, "skipped": False}

        def hold_lock():
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                with pipeline_lock():
                    results["held"] = True
                    time.sleep(0.3)

        def try_lock():
            time.sleep(0.1)  # Let the first thread acquire first
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                try:
                    with pipeline_lock():
                        pass  # pragma: no cover
                except RuntimeError as e:
                    if "cycle_skipped_overlap" in str(e):
                        results["skipped"] = True

        t1 = threading.Thread(target=hold_lock)
        t2 = threading.Thread(target=try_lock)

        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results["held"] is True
        assert results["skipped"] is True

    def test_lock_path_default_value(self):
        """LOCK_PATH points to memos/state/pipeline.lock relative to project root."""
        assert LOCK_PATH.name == "pipeline.lock"
        assert LOCK_PATH.parent.name == "state"
        assert LOCK_PATH.parent.parent.name == "memos"
