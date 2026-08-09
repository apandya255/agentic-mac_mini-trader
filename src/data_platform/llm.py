"""
LLM Gateway — All model calls route through OpenClaw.

This module provides a single function for making LLM calls that always
goes through the local OpenClaw gateway, respecting configured models,
auth profiles, rate limits, and audit logging.

Usage:
    from data_platform.llm import call_llm

    response = call_llm(
        message="Analyze this stock...",
        system_prompt="You are a financial analyst...",
        model=None,  # uses OpenClaw default (kimi-k3)
    )
"""
import json
import subprocess
import tempfile
from pathlib import Path


def call_llm(
    message: str,
    system_prompt: str | None = None,
    model: str | None = None,
    timeout: int = 120,
    json_output: bool = False,
) -> str | None:
    """
    Call an LLM through the OpenClaw gateway.

    Args:
        message: The user message / task prompt.
        system_prompt: Optional system prompt (prepended to message).
        model: OpenRouter model ID override (e.g. 'openrouter/openai/gpt-4o').
               If None, uses OpenClaw's configured default.
        timeout: Max seconds to wait for response.
        json_output: If True, returns parsed JSON dict instead of raw text.

    Returns:
        The assistant's response text, or None on failure.
    """
    # Build the full prompt (openclaw agent --local takes a single message)
    if system_prompt:
        full_message = f"{system_prompt}\n\n---\n\n{message}"
    else:
        full_message = message

    # Write message to a temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(full_message)
        prompt_path = f.name

    cmd = [
        "openclaw", "agent", "--local",
        "--message-file", prompt_path,
        "--json",
    ]

    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Clean up temp file
        Path(prompt_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return None

        # Parse JSON output from openclaw
        try:
            data = json.loads(result.stdout)
            text = (
                data.get("finalAssistantVisibleText")
                or data.get("finalAssistantRawText")
                or data.get("result", {}).get("finalAssistantVisibleText")
                or ""
            )
            if json_output:
                # Try to parse the response as JSON
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text
        except json.JSONDecodeError:
            # If --json flag didn't produce JSON, return raw stdout
            return result.stdout.strip() or None

    except subprocess.TimeoutExpired:
        Path(prompt_path).unlink(missing_ok=True)
        return None
    except Exception:
        Path(prompt_path).unlink(missing_ok=True)
        return None
