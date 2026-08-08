#!/usr/bin/env python3
"""
Full Desk Run — runs Saturday 10:00 ET via launchd.

Triggers the complete agent pipeline covering all fund_* and macro_* agents.
No holiday check needed — Saturday is never a market holiday (US markets are
closed weekends; this is analysis prep for Monday).

Workflow:
  1. Log cycle start
  2. Invoke run_cycle.py with no agent filter (all agents run)
  3. On success: log structured cycle entry with duration
  4. On failure: capture stderr and write to memos/logs/

Requirements: 10.1, 10.2, 10.3, 10.6
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.cycle_logger import log_cycle

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("full_desk_run")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """
    Full desk run entry point.

    Invokes run_cycle.py with no agent filter so all fund_* and macro_*
    agents participate. Wraps execution with structured logging capturing
    start time, duration, and success/failure status.
    """
    cycle_start = time.time()
    logger.info("Starting full desk run — all agents.")

    run_cycle_path = PROJECT_ROOT / "run_cycle.py"
    cmd = [sys.executable, str(run_cycle_path)]

    logger.info(f"Invoking: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
            timeout=7200,  # 2 hour max for full desk run
        )

        duration = time.time() - cycle_start
        logger.info(f"Full desk run completed successfully in {duration:.1f}s.")
        log_cycle(
            cycle_type="full_desk_run",
            status="success",
            duration_seconds=duration,
            metrics={
                "stdout_lines": len(result.stdout.splitlines()) if result.stdout else 0,
            },
            trigger_source="launchd",
        )

    except subprocess.CalledProcessError as e:
        duration = time.time() - cycle_start
        stderr_snippet = e.stderr[:2000] if e.stderr else "Non-zero exit code"
        logger.error(
            f"Full desk run failed (exit code {e.returncode}). "
            f"stderr: {stderr_snippet[:500]}"
        )
        log_cycle(
            cycle_type="full_desk_run",
            status="failure",
            duration_seconds=duration,
            metrics={
                "exit_code": e.returncode,
            },
            error=stderr_snippet,
            trigger_source="launchd",
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - cycle_start
        logger.error("Full desk run timed out after 2 hours.")
        log_cycle(
            cycle_type="full_desk_run",
            status="failure",
            duration_seconds=duration,
            metrics={},
            error="Timeout: exceeded 7200s limit",
            trigger_source="launchd",
        )

    except Exception as e:
        duration = time.time() - cycle_start
        logger.error(f"Full desk run encountered unexpected error: {e}")
        log_cycle(
            cycle_type="full_desk_run",
            status="failure",
            duration_seconds=duration,
            metrics={},
            error=str(e),
            trigger_source="launchd",
        )


if __name__ == "__main__":
    main()
