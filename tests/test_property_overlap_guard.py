# Feature: operational-reliability, Property 5: Overlap Guard Mutual Exclusion
"""
Property-based tests for overlap guard mutual exclusion.

For any two concurrent pipeline invocations, exactly one SHALL acquire the lock
and execute, while the other SHALL exit with "cycle_skipped_overlap"
(raises RuntimeError) and exit code 0.

Validates: Requirements 4.3, 4.4
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from src.trading.overlap_guard import pipeline_lock


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Number of concurrent pipeline invocations (2 to 4, kept small for threading)
num_concurrent_strategy = st.integers(min_value=2, max_value=4)


# ---------------------------------------------------------------------------
# Property 5: Overlap Guard Mutual Exclusion
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=30000)
@given(num_concurrent=num_concurrent_strategy)
def test_property_5_overlap_guard_mutual_exclusion(num_concurrent: int):
    """
    **Validates: Requirements 4.3, 4.4**

    Property 5: Overlap Guard Mutual Exclusion — For any N concurrent
    pipeline invocations (N in 2..4), exactly one SHALL acquire the lock
    and execute, while exactly N-1 SHALL raise RuntimeError("cycle_skipped_overlap").
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lock_file = Path(tmp_dir) / "pipeline.lock"

        # Track results from each thread
        results = {"acquired": 0, "skipped": 0}
        results_lock = threading.Lock()

        # Coordination: holder signals when it has the lock,
        # contenders signal when they have all finished attempting.
        holder_acquired = threading.Event()
        contenders_done = threading.Event()

        def hold_lock():
            """First thread: acquire lock, signal others, wait for them."""
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                try:
                    with pipeline_lock():
                        with results_lock:
                            results["acquired"] += 1
                        # Signal that lock is held
                        holder_acquired.set()
                        # Wait until all contenders have attempted
                        contenders_done.wait(timeout=10)
                except RuntimeError as e:
                    if "cycle_skipped_overlap" in str(e):
                        with results_lock:
                            results["skipped"] += 1
                        holder_acquired.set()

        def contend_lock():
            """Contender: wait for holder to acquire, then attempt lock."""
            holder_acquired.wait(timeout=10)
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                try:
                    with pipeline_lock():
                        with results_lock:
                            results["acquired"] += 1
                except RuntimeError as e:
                    if "cycle_skipped_overlap" in str(e):
                        with results_lock:
                            results["skipped"] += 1

        # Start the holder thread
        holder_thread = threading.Thread(target=hold_lock)
        holder_thread.start()

        # Start contender threads (num_concurrent - 1 contenders)
        contender_threads = []
        for _ in range(num_concurrent - 1):
            t = threading.Thread(target=contend_lock)
            contender_threads.append(t)
            t.start()

        # Wait for all contenders to finish
        for t in contender_threads:
            t.join(timeout=10)

        # Signal the holder that contenders are done so it can release
        contenders_done.set()
        holder_thread.join(timeout=10)

        # Invariant: exactly 1 acquires the lock, exactly N-1 are skipped
        assert results["acquired"] == 1, (
            f"Expected exactly 1 acquisition but got {results['acquired']} "
            f"with {num_concurrent} concurrent attempts"
        )
        assert results["skipped"] == num_concurrent - 1, (
            f"Expected {num_concurrent - 1} skips but got {results['skipped']} "
            f"with {num_concurrent} concurrent attempts"
        )
