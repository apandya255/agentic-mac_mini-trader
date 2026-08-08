"""Unit tests for scripts/daily_sweep.py

Validates: Requirements 11.1, 11.2, 11.3, 11.6
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load the daily_sweep module from the scripts directory
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("daily_sweep", _SCRIPTS_DIR / "daily_sweep.py")
daily_sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_sweep)


class TestGetActiveSectors:
    """Tests for get_active_sectors()."""

    def test_returns_sectors_for_active_positions(self):
        """Active positions map to their correct sectors."""
        mock_book = {
            "positions": [
                {"ticker": "XOM", "hedge_ticker": "RSPG", "status": "active"},
                {"ticker": "V", "hedge_ticker": "RSPF", "status": "active"},
            ]
        }
        with patch.object(daily_sweep, "load_book", return_value=mock_book):
            sectors = daily_sweep.get_active_sectors()

        assert "energy" in sectors
        assert "financials" in sectors

    def test_ignores_closed_positions(self):
        """Closed positions are not included in sector mapping."""
        mock_book = {
            "positions": [
                {"ticker": "XOM", "hedge_ticker": "RSPG", "status": "closed"},
                {"ticker": "V", "hedge_ticker": "RSPF", "status": "active"},
            ]
        }
        with patch.object(daily_sweep, "load_book", return_value=mock_book):
            sectors = daily_sweep.get_active_sectors()

        assert "energy" not in sectors
        assert "financials" in sectors

    def test_returns_empty_list_when_no_positions(self):
        """Empty book returns no sectors."""
        mock_book = {"positions": []}
        with patch.object(daily_sweep, "load_book", return_value=mock_book):
            sectors = daily_sweep.get_active_sectors()

        assert sectors == []

    def test_deduplicates_sectors(self):
        """Multiple positions in the same sector produce one entry."""
        mock_book = {
            "positions": [
                {"ticker": "XOM", "hedge_ticker": "RSPG", "status": "active"},
                {"ticker": "DVN", "hedge_ticker": "RSPG", "status": "active"},
            ]
        }
        with patch.object(daily_sweep, "load_book", return_value=mock_book):
            sectors = daily_sweep.get_active_sectors()

        assert sectors.count("energy") == 1


class TestGetRelevantAgents:
    """Tests for get_relevant_agents()."""

    def test_single_sector_maps_to_fund_and_macro(self):
        """A single sector maps to its fund agent plus macro agents."""
        agents = daily_sweep.get_relevant_agents(["energy"])

        assert "fund_energy" in agents
        assert "macro_northamerica" in agents
        assert "macro_commodities" in agents

    def test_multiple_sectors_deduplicate_macro(self):
        """Multiple sectors don't duplicate shared macro agents."""
        agents = daily_sweep.get_relevant_agents(["energy", "financials"])

        # macro_northamerica appears in both but should only be listed once
        assert agents.count("macro_northamerica") == 1
        assert "fund_energy" in agents
        assert "fund_financials" in agents

    def test_always_includes_macro_northamerica(self):
        """macro_northamerica is always included as baseline."""
        agents = daily_sweep.get_relevant_agents(["real estate"])
        assert "macro_northamerica" in agents

    def test_consumer_discretionary_includes_asia(self):
        """Consumer discretionary sector includes macro_asia."""
        agents = daily_sweep.get_relevant_agents(["consumer discretionary"])
        assert "macro_asia" in agents
        assert "fund_consdisc" in agents

    def test_empty_sectors_returns_only_macro_northamerica(self):
        """Empty sector list returns only the baseline macro agent."""
        agents = daily_sweep.get_relevant_agents([])
        assert agents == ["macro_northamerica"]


class TestMainHolidaySkip:
    """Tests for main() holiday skip behavior."""

    @patch.object(daily_sweep, "log_cycle")
    @patch.object(daily_sweep, "is_trading_day", return_value=False)
    def test_skips_on_holiday(self, mock_trading_day, mock_log_cycle):
        """Main skips execution and logs when not a trading day."""
        daily_sweep.main()

        mock_log_cycle.assert_called_once()
        call_kwargs = mock_log_cycle.call_args[1]
        assert call_kwargs["cycle_type"] == "daily_sweep"
        assert call_kwargs["status"] == "skipped"


class TestMainNoPositions:
    """Tests for main() with no active positions."""

    @patch("subprocess.run")
    @patch.object(daily_sweep, "log_cycle")
    @patch.object(daily_sweep, "is_trading_day", return_value=True)
    @patch.object(daily_sweep, "load_book", return_value={"positions": []})
    def test_runs_default_macro_only(self, mock_book, mock_trading_day, mock_log_cycle, mock_run):
        """When no positions exist, only default macro agents are invoked."""
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        daily_sweep.main()

        # Verify subprocess was called with the default macro agents
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        agents_arg = cmd[cmd.index("--agents") + 1]
        agent_list = agents_arg.split(",")

        assert "macro_northamerica" in agent_list
        assert "macro_westerneurope" in agent_list
        assert "macro_asia" in agent_list
        # No fund_* agents
        assert not any(a.startswith("fund_") for a in agent_list)
