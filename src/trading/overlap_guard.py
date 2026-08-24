"""
Overlap guard for pipeline mutual exclusion.

Prevents concurrent pipeline executions by acquiring an exclusive file lock.
If a pipeline cycle is already running, the duplicate trigger is skipped
with a RuntimeError("cycle_skipped_overlap") event.

Requirements: 7.5
"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

LOCK_PATH = Path(__file__).parent.parent.parent / "memos" / "state" / "pipeline.lock"


@contextmanager
def pipeline_lock():
    """
    Acquire an exclusive file lock for the pipeline.

    Uses fcntl.flock with LOCK_EX | LOCK_NB to attempt a non-blocking
    exclusive lock on the lock file at memos/state/pipeline.lock.
    Writes the current PID to the lock file while the lock is held.

    Yields:
        None — the lock is held for the duration of the context.

    Raises:
        RuntimeError: With message "cycle_skipped_overlap" if the lock
            cannot be acquired (another cycle is already running).
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        lock_fd.close()
        raise RuntimeError("cycle_skipped_overlap")
    try:
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        yield
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
