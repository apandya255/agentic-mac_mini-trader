# Feature: operational-reliability, Property 12: Telegram Severity Prefix Invariant
"""
Property-based tests for Telegram severity prefix invariant.

Property 12: For all alert messages delivered via the Telegram notifier,
the message text SHALL be prefixed with "CRITICAL:", "WARNING:", or "INFO:"
matching its severity level, with no other prefix format.

**Validates: Requirements 13.4**
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.telegram_bot import send_message


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

severity_strategy = st.sampled_from(["critical", "warning", "info"])
message_text_strategy = st.text(
    min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",))
)

# Expected prefix mapping
EXPECTED_PREFIXES = {
    "critical": "CRITICAL:",
    "warning": "WARNING:",
    "info": "INFO:",
}


# ---------------------------------------------------------------------------
# Property 12: Telegram Severity Prefix Invariant
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(severity=severity_strategy, message_text=message_text_strategy)
def test_property_12_telegram_severity_prefix_invariant(
    severity: str, message_text: str
):
    """
    **Validates: Requirements 13.4**

    Property 12: For all severity values and message texts:
      1. The sent text starts with the correct prefix (CRITICAL:, WARNING:, INFO:)
      2. The original message content appears after the prefix
      3. If the message already starts with the correct prefix, it is NOT doubled
    """
    sent_texts: list[str] = []

    def mock_post_message(token: str, chat_id: str, text: str) -> bool:
        sent_texts.append(text)
        return True

    def mock_get_config() -> tuple[str, str]:
        return ("fake_token", "fake_chat_id")

    with patch("src.telegram_bot._get_config", side_effect=mock_get_config), \
         patch("src.telegram_bot._post_message", side_effect=mock_post_message):
        send_message(message_text, severity=severity)

    expected_prefix = EXPECTED_PREFIXES[severity]

    # All chunks should have been sent (message is <= 200 chars, fits in one chunk)
    assert len(sent_texts) >= 1, "Expected at least one message to be sent"

    # Check the first sent text (which contains the prefix)
    sent_text = sent_texts[0]

    # 1. The sent text must start with the correct prefix
    assert sent_text.startswith(expected_prefix), (
        f"Expected message to start with '{expected_prefix}' for severity='{severity}', "
        f"but got: {sent_text[:50]!r}"
    )

    # 2. The original message content must appear after the prefix
    after_prefix = sent_text[len(expected_prefix):]
    # The message is prefixed with "PREFIX: " (note the space after colon)
    # If the original message already started with the prefix, no doubling occurs
    if message_text.startswith(expected_prefix):
        # No doubling: sent text should be exactly the original message
        assert sent_text == message_text, (
            f"Expected no prefix doubling. Message already starts with '{expected_prefix}', "
            f"sent text should be the original message. Got: {sent_text[:80]!r}"
        )
    else:
        # Normal case: prefix + space + original message
        expected_full = f"{expected_prefix} {message_text}"
        assert sent_text == expected_full, (
            f"Expected '{expected_prefix} <message>', "
            f"got: {sent_text[:80]!r}"
        )

    # 3. Verify no other prefix format is applied (no double-prefix)
    # After removing the correct prefix, the remainder should NOT start with another prefix
    for other_prefix in EXPECTED_PREFIXES.values():
        if other_prefix != expected_prefix:
            assert not sent_text.startswith(other_prefix), (
                f"Message should not start with wrong prefix '{other_prefix}' "
                f"for severity='{severity}'"
            )
