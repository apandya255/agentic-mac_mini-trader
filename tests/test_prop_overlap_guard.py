# Feature: autonomous-trading-loop, Property 12: Pipeline overlap guard ensures mutual exclusion
"""
Property-based tests for src/trading/overlap_guard.py

Property 12: Pipeline overlap guard ensures mutual exclusion
For any number of concurrent pipeline cycle triggers, at most one SHALL execute.
The second (and subsequent) SHALL be skipped with a RuntimeError("cycle_skipped_overlap").

**Validates: Requirements 7.5**
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.trading.overlap_guard import pipeline_lock

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for number of concurrent threads attempting the lock (2 to 5)
num_concurrent_strategy = st.integers(min_value=2, max_value=5)


# ---------------------------------------------------------------------------
# Property 12: Pipeline overlap guard ensures mutual exclusion
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=30000)
@given(
    num_concurrent=num_concurrent_strategy,
)
def test_property_12_at_most_one_concurrent_execution(
    num_concurrent: int,
):
    """
    **Validates: Requirements 7.5**

    Property 12: For any number of concurrent attempts (2-5) to acquire
    the pipeline lock, at most one succeeds. All additional attempts
    raise RuntimeError("cycle_skipped_overlap").
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lock_file = Path(tmp_dir) / "pipeline.lock"

        # Track results: how many succeeded vs how many were skipped
        results = {"acquired": 0, "skipped": 0}
        results_lock = threading.Lock()

        # Use events to coordinate: the holder signals when it has the lock,
        # and contenders signal when they have all finished attempting.
        holder_acquired = threading.Event()
        contenders_done = threading.Event()

        def hold_lock():
            """First thread: acquire lock, signal others, wait for them to finish."""
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
            """Contender thread: wait for holder to acquire, then attempt lock."""
            # Wait for the holder to have the lock before attempting
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

        # Mutual exclusion: exactly one acquired, the rest were skipped
        assert results["acquired"] == 1, (
            f"Expected exactly 1 acquisition but got {results['acquired']} "
            f"with {num_concurrent} concurrent attempts"
        )
        assert results["skipped"] == num_concurrent - 1, (
            f"Expected {num_concurrent - 1} skips but got {results['skipped']} "
            f"with {num_concurrent} concurrent attempts"
        )


@settings(max_examples=50, deadline=10000)
@given(
    num_concurrent=num_concurrent_strategy,
)
def test_property_12_lock_reacquirable_after_release(
    num_concurrent: int,
):
    """
    **Validates: Requirements 7.5**

    Property 12 (sub-property): After the first thread releases the lock,
    it can be re-acquired by another thread. This confirms the guard only
    blocks concurrent (overlapping) executions, not sequential ones.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lock_file = Path(tmp_dir) / "pipeline.lock"

        # Phase 1: First thread holds and releases the lock
        with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
            with pipeline_lock():
                # Lock held — verify file has PID
                assert lock_file.exists()

        # Phase 2: Multiple sequential acquisitions should all succeed
        success_count = 0
        for _ in range(num_concurrent):
            with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                with pipeline_lock():
                    success_count += 1

        assert success_count == num_concurrent, (
            f"Expected {num_concurrent} sequential acquisitions to succeed, "
            f"but only {success_count} did"
        )


@settings(max_examples=30, deadline=15000)
@given(
    num_concurrent=num_concurrent_strategy,
)
def test_property_12_second_wave_succeeds_after_first_wave_completes(
    num_concurrent: int,
):
    """
    **Validates: Requirements 7.5**

    Property 12 (sub-property): After all concurrent threads from wave 1
    complete (one succeeds, rest skip), a new wave of threads can again
    have exactly one succeed — proving the lock is properly released.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lock_file = Path(tmp_dir) / "pipeline.lock"

        def run_wave() -> dict:
            """Run a wave of concurrent lock attempts and return results."""
            wave_results = {"acquired": 0, "skipped": 0}
            results_lock = threading.Lock()

            def attempt(delay: float):
                time.sleep(delay)
                with patch("src.trading.overlap_guard.LOCK_PATH", lock_file):
                    try:
                        with pipeline_lock():
                            with results_lock:
                                wave_results["acquired"] += 1
                            time.sleep(0.1)
                    except RuntimeError as e:
                        if "cycle_skipped_overlap" in str(e):
                            with results_lock:
                                wave_results["skipped"] += 1

            threads = []
            for i in range(num_concurrent):
                threads.append(threading.Thread(target=attempt, args=(0.02 * i,)))
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
            return wave_results

        # Wave 1
        wave1 = run_wave()
        assert wave1["acquired"] == 1, (
            f"Wave 1: expected 1 acquisition, got {wave1['acquired']}"
        )
        assert wave1["skipped"] == num_concurrent - 1

        # Wave 2 — lock should be released, so one thread can succeed again
        wave2 = run_wave()
        assert wave2["acquired"] == 1, (
            f"Wave 2: expected 1 acquisition after wave 1 completed, "
            f"got {wave2['acquired']}"
        )
        assert wave2["skipped"] == num_concurrent - 1
