"""Structured cycle logging for all automated processes.

Writes JSON log entries to memos/logs/{cycle_type}_{ISO_timestamp}.json
with a consistent schema for observability and dashboard consumption.

Requirements: 18.1, 18.2, 18.5
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
