"""
Unit tests for CB Decision Monitoring (Task 12.7).

Validates that the price poller correctly:
- Parses desk/rates_table.md for scheduled CB decision dates
- Checks if a decision is within ±1 hour (i.e., today) and calls Brave search
- Sends Telegram alert when outcome is off-consensus
- Skips alerting when outcome matches consensus
- Deduplicates alerts for the same decision
- Degrades gracefully when BRAVE_API_KEY is not configured

**Validates: Requirements 21.1, 21.2, 21.3**
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.price_poller import (
    _parse_rates_table,
    _parse_rate_from_text,
    _determine_consensus_rate,
    _check_cb_outcome,
    handle_cb_decisions,
    _cb_decisions_alerted,
    RATES_TABLE_PATH,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RATES_TABLE = """# Policy Rates — desk/rates_table.md

| CCY | Policy rate % | As of (last change) | Next decision | CB | Owner seat |
|-----|---------------|---------------------|---------------|-----|------------|
| USD | 4.25-4.50 | 2026-06-18 | {today} | Fed | North America |
| EUR | 3.65 | 2026-06-05 | 2026-12-31 | ECB | Western Europe |
| JPY | 0.50 | 2026-03-14 | {today} | BoJ | Asia |
| CNY | 1.40 | 2026-05-20 | — | PBoC (7d reverse repo as anchor) | Asia |
"""


def sample_rates_table_today():
    """Return a rates table with decisions today."""
    today_str = date.today().isoformat()
    return SAMPLE_RATES_TABLE.replace("{today}", today_str)


def sample_rates_table_future():
    """Return a rates table with no decisions today."""
    return SAMPLE_RATES_TABLE.replace("{today}", "2099-12-31")


# ---------------------------------------------------------------------------
# Tests: _parse_rates_table
# ---------------------------------------------------------------------------


class TestParseRatesTable:
    @patch("scripts.price_poller.RATES_TABLE_PATH")
    def test_parses_valid_entries(self, mock_path):
        """Should parse valid rows from rates table."""
        today_str = date.today().isoformat()
        content = sample_rates_table_today()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = content

        result = _parse_rates_table()

        assert len(result) >= 3  # USD, EUR, JPY (not CNY — has "—")
        usd_entry = next(e for e in result if e["ccy"] == "USD")
        assert usd_entry["rate"] == "4.25-4.50"
        assert usd_entry["next_decision"] == today_str
        assert usd_entry["cb"] == "Fed"

    @patch("scripts.price_poller.RATES_TABLE_PATH")
    def test_skips_dash_next_decision(self, mock_path):
        """Should skip entries with '—' as next decision."""
        content = sample_rates_table_today()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = content

        result = _parse_rates_table()

        ccys = [e["ccy"] for e in result]
        assert "CNY" not in ccys

    @patch("scripts.price_poller.RATES_TABLE_PATH")
    def test_returns_empty_if_file_missing(self, mock_path):
        """Should return empty list if rates_table.md doesn't exist."""
        mock_path.exists.return_value = False

        result = _parse_rates_table()

        assert result == []


# ---------------------------------------------------------------------------
# Tests: _parse_rate_from_text
# ---------------------------------------------------------------------------


class TestParseRateFromText:
    def test_parses_raised_to_rate(self):
        """Should extract rate from 'raised to X%' pattern."""
        text = "Fed raised rates to 4.75% in latest decision"
        assert _parse_rate_from_text(text) == 4.75

    def test_parses_cut_to_rate(self):
        """Should extract rate from 'cut to X%' pattern."""
        text = "ECB cuts rate to 3.50% from 3.65%"
        assert _parse_rate_from_text(text) == 3.50

    def test_parses_held_at_rate(self):
        """Should extract rate from 'held at X%' pattern."""
        text = "BoJ held rate unchanged at 0.50%"
        assert _parse_rate_from_text(text) == 0.50

    def test_parses_range_format(self):
        """Should parse range format and return upper bound."""
        text = "New target range 4.50-4.75 percent"
        result = _parse_rate_from_text(text)
        assert result == 4.75

    def test_returns_none_for_unparseable(self):
        """Should return None when no rate can be extracted."""
        text = "Markets await decision from central bank"
        assert _parse_rate_from_text(text) is None


# ---------------------------------------------------------------------------
# Tests: _determine_consensus_rate
# ---------------------------------------------------------------------------


class TestDetermineConsensusRate:
    def test_parses_range_upper_bound(self):
        """Should return upper bound for range format."""
        assert _determine_consensus_rate("4.25-4.50") == 4.50

    def test_parses_single_value(self):
        """Should return the value for single rate format."""
        assert _determine_consensus_rate("3.65") == 3.65

    def test_handles_zero_rate(self):
        """Should handle zero rate correctly."""
        assert _determine_consensus_rate("0.50") == 0.50

    def test_returns_none_for_invalid(self):
        """Should return None for unparseable strings."""
        assert _determine_consensus_rate("—") is None


# ---------------------------------------------------------------------------
# Tests: _check_cb_outcome
# ---------------------------------------------------------------------------


class TestCheckCBOutcome:
    @patch("scripts.price_poller._brave_search_cb")
    def test_returns_none_when_no_results(self, mock_search):
        """Should return None when Brave search returns no results."""
        mock_search.return_value = []

        result = _check_cb_outcome("Fed", "USD", "4.25-4.50")

        assert result is None

    @patch("scripts.price_poller._brave_search_cb")
    def test_detects_announced_rate_hike(self, mock_search):
        """Should detect an announced rate decision."""
        mock_search.return_value = [
            {
                "title": "Fed raises rates to 4.75% in surprise move",
                "url": "https://example.com/fed",
                "description": "The Federal Reserve raised its target range to 4.50-4.75%",
            }
        ]

        result = _check_cb_outcome("Fed", "USD", "4.25-4.50")

        assert result is not None
        assert result["announced"] is True
        assert result["actual_rate"] == 4.75

    @patch("scripts.price_poller._brave_search_cb")
    def test_returns_not_announced_for_irrelevant_results(self, mock_search):
        """Should return announced=False when results don't mention a decision."""
        mock_search.return_value = [
            {
                "title": "Markets await Fed decision today",
                "url": "https://example.com/preview",
                "description": "Investors are positioned for a hold scenario.",
            }
        ]

        result = _check_cb_outcome("Fed", "USD", "4.25-4.50")

        assert result is not None
        assert result["announced"] is False


# ---------------------------------------------------------------------------
# Tests: handle_cb_decisions (integration)
# ---------------------------------------------------------------------------


class TestHandleCBDecisions:
    def setup_method(self):
        """Clear the alerted state before each test."""
        _cb_decisions_alerted.clear()

    @patch("scripts.price_poller.BRAVE_API_KEY", "")
    @patch("scripts.price_poller.logger")
    def test_skips_without_brave_api_key(self, mock_logger):
        """Should skip gracefully without BRAVE_API_KEY."""
        handle_cb_decisions({})
        # Should not raise, just log debug and return

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_sends_alert_on_off_consensus(self, mock_telegram, mock_outcome, mock_table):
        """Should send Telegram alert when CB decision is off-consensus."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "USD", "rate": "4.25-4.50", "next_decision": today_str, "cb": "Fed"},
        ]
        mock_outcome.return_value = {
            "announced": True,
            "actual_rate": 4.75,
            "summary": "Fed raises to 4.75%",
        }

        handle_cb_decisions({})

        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args[0][0]
        assert "OFF-CONSENSUS" in call_args
        assert "4.75" in call_args
        assert "+25 bp" in call_args

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_no_alert_when_in_line(self, mock_telegram, mock_outcome, mock_table):
        """Should NOT send alert when decision matches consensus."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "USD", "rate": "4.25-4.50", "next_decision": today_str, "cb": "Fed"},
        ]
        mock_outcome.return_value = {
            "announced": True,
            "actual_rate": 4.50,
            "summary": "Fed holds at 4.50%",
        }

        handle_cb_decisions({})

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_dedup_prevents_repeat_alert(self, mock_telegram, mock_outcome, mock_table):
        """Should not re-alert for the same CB decision."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "USD", "rate": "4.25-4.50", "next_decision": today_str, "cb": "Fed"},
        ]
        mock_outcome.return_value = {
            "announced": True,
            "actual_rate": 4.75,
            "summary": "Fed raises to 4.75%",
        }

        # First call — should alert
        handle_cb_decisions({})
        assert mock_telegram.call_count == 1

        # Second call — should NOT alert (dedup)
        handle_cb_decisions({})
        assert mock_telegram.call_count == 1

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_skips_future_decisions(self, mock_telegram, mock_outcome, mock_table):
        """Should skip decisions not scheduled for today."""
        mock_table.return_value = [
            {"ccy": "EUR", "rate": "3.65", "next_decision": "2099-12-31", "cb": "ECB"},
        ]

        handle_cb_decisions({})

        mock_outcome.assert_not_called()
        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_handles_not_yet_announced(self, mock_telegram, mock_outcome, mock_table):
        """Should do nothing when decision is today but not yet announced."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "JPY", "rate": "0.50", "next_decision": today_str, "cb": "BoJ"},
        ]
        mock_outcome.return_value = {
            "announced": False,
            "actual_rate": None,
            "summary": "",
        }

        handle_cb_decisions({})

        mock_telegram.assert_not_called()
        # Should NOT be in alerted dict (so it checks again next cycle)
        assert "BoJ_" + today_str not in _cb_decisions_alerted

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_sends_alert_when_rate_not_parseable(self, mock_telegram, mock_outcome, mock_table):
        """Should alert with 'could not parse' when rate extraction fails."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "USD", "rate": "4.25-4.50", "next_decision": today_str, "cb": "Fed"},
        ]
        mock_outcome.return_value = {
            "announced": True,
            "actual_rate": None,  # Could not parse
            "summary": "Fed announces decision",
        }

        handle_cb_decisions({})

        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args[0][0]
        assert "could not be parsed" in call_args

    @patch("scripts.price_poller.BRAVE_API_KEY", "test-key")
    @patch("scripts.price_poller._parse_rates_table")
    @patch("scripts.price_poller._check_cb_outcome")
    @patch("scripts.price_poller.send_telegram")
    def test_sends_alert_for_rate_cut(self, mock_telegram, mock_outcome, mock_table):
        """Should send alert with negative bp diff for a cut."""
        today_str = date.today().isoformat()
        mock_table.return_value = [
            {"ccy": "EUR", "rate": "3.65", "next_decision": today_str, "cb": "ECB"},
        ]
        mock_outcome.return_value = {
            "announced": True,
            "actual_rate": 3.40,
            "summary": "ECB cuts by 25bp",
        }

        handle_cb_decisions({})

        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args[0][0]
        assert "OFF-CONSENSUS" in call_args
        assert "-25 bp" in call_args
        assert "lower" in call_args
