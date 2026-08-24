"""
Service restart logging for launchd-managed services.

Appends restart events to memos/logs/service_restarts.log.
Format: {timestamp} {service_name} restarted (previous exit code: {code}, signal: {signal})

Requirements: 12.4
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

RESTART_LOG = Path(__file__).parent.parent.parent / "memos" / "logs" / "service_restarts.log"


def log_service_restart(
    service_name: str,
    exit_code: int | None = None,
    signal: str | None = None,
) -> None:
    """Append a restart event to the service restarts log.

    Args:
        service_name: Name of the service (e.g., "serve.py", "cloudflared")
        exit_code: Previous exit code of the crashed service (if known)
        signal: Signal that killed the service (if known)
    """
    RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    code_str = str(exit_code) if exit_code is not None else "unknown"
    signal_str = signal if signal else "None"

    line = f"{timestamp} {service_name} restarted (previous exit code: {code_str}, signal: {signal_str})\n"

    with open(RESTART_LOG, "a") as f:
        f.write(line)


if __name__ == "__main__":
    import sys

    service_name = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    exit_code = int(sys.argv[2]) if len(sys.argv) > 2 else None
    signal_name = sys.argv[3] if len(sys.argv) > 3 else None
    log_service_restart(service_name, exit_code, signal_name)
