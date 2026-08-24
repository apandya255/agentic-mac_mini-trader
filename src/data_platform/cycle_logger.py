"""Structured cycle logging for all automated processes.

Writes JSON log entries to memos/logs/{cycle_type}_{ISO_timestamp}.json
with a consistent schema for observability and dashboard consumption.

Also provides per-pipeline-cycle structured logging with phase tracking
(log_cycle_start, log_phase_complete, log_cycle_complete) writing to
memos/logs/cycle_{timestamp}.json.

Requirements: 14.1, 14.2, 14.3, 14.4, 18.1, 18.2, 18.5
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve the logs directory relative to the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = _PROJECT_ROOT / "memos" / "logs"


def log_cycle(
    cycle_type: str,
    status: str,
    duration_seconds: float,
    metrics: dict,
    error: Optional[str] = None,
    trigger_source: str = "launchd",
) -> Path:
    """Write a structured JSON log entry for a completed automation cycle.

    Args:
        cycle_type: One of "price_poll", "daily_sweep", "full_desk_run", or
                    any other cycle identifier.
        status: Outcome — "success", "failure", or "skipped".
        duration_seconds: Wall-clock time the cycle took.
        metrics: Dict of cycle-specific metrics (e.g. tickers_updated,
                 proposals_generated, orders_written).
        error: Error message string if status is "failure"; None otherwise.
        trigger_source: How the cycle was triggered — "launchd" or "manual".

    Returns:
        Path to the written log file.
    """
    now = datetime.now(timezone.utc).astimezone()
    iso_ts = now.isoformat()

    entry = {
        "timestamp": iso_ts,
        "cycle_type": cycle_type,
        "trigger_source": trigger_source,
        "status": status,
        "duration_seconds": round(duration_seconds, 3),
        "metrics": metrics,
        "error": error,
    }

    # File naming: {cycle_type}_{ISO_timestamp}.json
    # Replace colons in timestamp for filesystem safety
    safe_ts = now.strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"{cycle_type}_{safe_ts}.json"

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / filename

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)

    return log_path


# ---------------------------------------------------------------------------
# Pipeline Cycle Structured Logger (Requirements 14.1–14.4)
# ---------------------------------------------------------------------------
# These functions implement per-pipeline-execution logging with a phases array
# and summary object, written to memos/logs/cycle_{timestamp}.json.


def _get_cycle_log_path(cycle_id: str) -> Path:
    """Get the log file path for a given cycle_id.

    The cycle_id is an ISO timestamp like '2025-07-15T09:40:00'.
    Colons and dashes are stripped for filesystem safety.
    """
    safe_id = cycle_id.replace(":", "").replace("-", "").replace("T", "_")
    return LOGS_DIR / f"cycle_{safe_id}.json"


def _read_cycle_log(cycle_id: str) -> dict:
    """Read existing cycle log from disk. Returns empty dict if absent."""
    path = _get_cycle_log_path(cycle_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _write_cycle_log(cycle_id: str, data: dict) -> None:
    """Write cycle log JSON to disk, creating directories as needed."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _get_cycle_log_path(cycle_id)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def log_cycle_start(trigger_source: str = "launchd") -> str:
    """Log cycle start. Returns cycle_id for correlating subsequent entries.

    Creates the initial log file with cycle_id, trigger_source, empty phases,
    and a null summary.

    Args:
        trigger_source: How the cycle was triggered — "launchd" or "manual".

    Returns:
        cycle_id (ISO timestamp string, e.g. '2025-07-15T09:40:00').
    """
    cycle_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    data = {
        "cycle_id": cycle_id,
        "trigger_source": trigger_source,
        "phases": [],
        "summary": None,
    }
    _write_cycle_log(cycle_id, data)
    logger.info("Cycle started: %s (trigger: %s)", cycle_id, trigger_source)
    return cycle_id


def log_phase_complete(
    cycle_id: str, phase: str, duration_s: float, outcome: str
) -> None:
    """Append phase completion record to the cycle log file.

    Args:
        cycle_id: The cycle_id returned by log_cycle_start().
        phase: Name of the phase (e.g. "data_refresh", "proposals").
        duration_s: Duration of the phase in seconds.
        outcome: Phase outcome — "success", "failure", or "skipped".
    """
    data = _read_cycle_log(cycle_id)
    if not data:
        logger.warning("Cycle log not found for %s, creating new entry", cycle_id)
        data = {
            "cycle_id": cycle_id,
            "trigger_source": "unknown",
            "phases": [],
            "summary": None,
        }

    data.setdefault("phases", []).append({
        "name": phase,
        "duration_s": round(duration_s, 2),
        "outcome": outcome,
    })
    _write_cycle_log(cycle_id, data)
    logger.info(
        "Phase complete: %s/%s (%.2fs, %s)", cycle_id, phase, duration_s, outcome
    )


def log_cycle_complete(
    cycle_id: str,
    total_duration_s: float,
    proposals: int,
    trades: int,
    exit_code: int,
) -> None:
    """Finalize cycle log with summary stats.

    Args:
        cycle_id: The cycle_id returned by log_cycle_start().
        total_duration_s: Total cycle duration in seconds.
        proposals: Number of proposals generated during the cycle.
        trades: Number of trades booked during the cycle.
        exit_code: Pipeline exit code (0 = success, 1 = failure).
    """
    data = _read_cycle_log(cycle_id)
    if not data:
        data = {
            "cycle_id": cycle_id,
            "trigger_source": "unknown",
            "phases": [],
            "summary": None,
        }

    data["summary"] = {
        "total_duration_s": round(total_duration_s, 2),
        "proposals_generated": proposals,
        "trades_booked": trades,
        "exit_code": exit_code,
    }
    _write_cycle_log(cycle_id, data)
    logger.info(
        "Cycle complete: %s (%.2fs, %d proposals, %d trades, exit=%d)",
        cycle_id,
        total_duration_s,
        proposals,
        trades,
        exit_code,
    )
