"""
Environment Loader — loads secrets from ~/.openclaw/.env per TOOLS.md security model.

TOOLS.md mandates: "API keys live in ~/.openclaw/.env and the gateway config —
never read, print, echo, or write them anywhere. Workspace .env is untrusted by
OpenClaw design; put nothing sensitive in it."

This module provides a single entry point for loading secrets into os.environ.
Scripts should call `load_secrets()` early at startup. If ~/.openclaw/.env does
not exist, the function is a no-op (secrets may already be in the environment
via launchd or shell profile).

Non-secret configuration (POLL_INTERVAL_MINUTES, model slugs, etc.) may still
be read directly from os.environ with defaults — they do not require this loader.
"""

from __future__ import annotations

import os
from pathlib import Path


# The canonical secrets file per TOOLS.md
SECRETS_ENV_PATH = Path.home() / ".openclaw" / ".env"


def load_secrets(env_path: Path | None = None) -> int:
    """Load secrets from ~/.openclaw/.env into os.environ.

    Uses setdefault so that environment variables already set (e.g., by
    launchd plist EnvironmentVariables or shell export) are not overwritten.

    Args:
        env_path: Override path for testing. Defaults to ~/.openclaw/.env.

    Returns:
        Number of variables loaded.
    """
    path = env_path or SECRETS_ENV_PATH

    if not path.exists():
        return 0

    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            # Strip surrounding quotes if present
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            os.environ.setdefault(key, val)
            count += 1
    except OSError:
        # If we can't read the file, proceed silently — secrets may
        # already be in environment via other means.
        pass

    return count
