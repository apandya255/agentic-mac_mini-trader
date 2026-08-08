"""
Telegram Bot — notification delivery for the Agentic Trading heartbeat.

Sends alerts, reports, and trade recommendations to a Telegram chat via
the Bot API. Handles the 4000-character message limit by splitting on
newline boundaries without truncating numbers. Implements retry-once on
delivery failure before marking as failed.

Environment variables:
    TELEGRAM_BOT_TOKEN: Bot API token from @BotFather
    TELEGRAM_CHAT_ID: Target chat/channel ID for delivery

Usage:
    from src.telegram_bot import send_message

    success = send_message("Trail breach: XOM closed at $112.45, P&L -2.7%")
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4000

# Structured log output directory
LOGS_DIR = Path(__file__).parent.parent / "memos" / "logs"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_config() -> tuple[str, str]:
    """Read Telegram credentials from environment.

    Returns:
        Tuple of (bot_token, chat_id).

    Raises:
        RuntimeError: If either variable is missing.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set in environment. "
            "Cannot deliver Telegram messages."
        )
    if not chat_id:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID not set in environment. "
            "Cannot deliver Telegram messages."
        )

    return token, chat_id


def _log_delivery(
    status: str,
    message_preview: str,
    attempt: int,
    error: str | None = None,
) -> None:
    """Write a structured log entry for a delivery attempt.

    Args:
        status: "success", "failure", or "retry"
        message_preview: First 80 chars of the message for context
        attempt: 1 or 2 (retry)
        error: Error string on failure, None on success
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle_type": "telegram_delivery",
        "trigger_source": "heartbeat",
        "status": status,
        "attempt": attempt,
        "message_preview": message_preview[:80],
        "error": error,
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = LOGS_DIR / f"telegram_delivery_{ts}.json"

    try:
        log_path.write_text(json.dumps(entry, indent=2))
    except OSError:
        # If we can't write logs, print to stderr as fallback
        print(f"[TELEGRAM] LOG WRITE FAILED: {entry}")


def _post_message(token: str, chat_id: str, text: str) -> bool:
    """Send a single message chunk via the Telegram Bot API.

    Uses urllib (no external dependency beyond stdlib) for the HTTP POST.

    Args:
        token: Bot API token.
        chat_id: Target chat ID.
        text: Message text (must be <= 4000 chars).

    Returns:
        True on success, False on failure.
    """
    url = TELEGRAM_API_BASE.format(token=token)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


# ---------------------------------------------------------------------------
# Message splitting
# ---------------------------------------------------------------------------


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks respecting newline boundaries.

    Rules:
    - Never split mid-line (always on newline boundaries)
    - Never truncate numbers — a line containing numeric data stays intact
    - If a single line exceeds max_length, it gets its own chunk (never truncated)
    - First chunk is the "headline" portion; subsequent are "detail" continuations

    Args:
        text: The full message text.
        max_length: Maximum character count per chunk (default 4000).

    Returns:
        List of message chunks, each within max_length (except for
        unavoidably long single lines).
    """
    if len(text) <= max_length:
        return [text]

    lines = text.split("\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        # +1 accounts for the newline character we'll add back
        line_length = len(line) + 1

        if current_length + line_length > max_length and current_chunk:
            # Flush the current chunk
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(line)
        current_length += line_length

    # Flush any remaining lines
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_message(text: str) -> bool:
    """Send a message to the configured Telegram chat.

    Handles:
    - 4000-char limit by splitting on newline boundaries
    - Retry-once on delivery failure before marking failed
    - Structured logging for all delivery attempts

    Args:
        text: The message to send (can exceed 4000 chars).

    Returns:
        True if all chunks delivered successfully, False if any failed
        after retry.
    """
    try:
        token, chat_id = _get_config()
    except RuntimeError as e:
        print(f"[TELEGRAM] Config error: {e}")
        _log_delivery("failure", text, attempt=1, error=str(e))
        return False

    chunks = split_message(text)
    all_success = True

    for i, chunk in enumerate(chunks):
        preview = chunk[:80].replace("\n", " ")
        success = _post_message(token, chat_id, chunk)

        if success:
            _log_delivery("success", preview, attempt=1)
        else:
            # Retry once
            _log_delivery("retry", preview, attempt=1, error="First attempt failed")
            print(f"[TELEGRAM] Chunk {i+1}/{len(chunks)} failed, retrying...")
            time.sleep(1)  # Brief pause before retry

            success = _post_message(token, chat_id, chunk)
            if success:
                _log_delivery("success", preview, attempt=2)
            else:
                _log_delivery("failure", preview, attempt=2, error="Retry also failed")
                print(f"[TELEGRAM] Chunk {i+1}/{len(chunks)} FAILED after retry")
                all_success = False

    return all_success
