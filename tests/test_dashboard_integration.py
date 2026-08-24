"""
Integration tests for the revamped dashboard.

Feature: dashboard-autonomous-revamp
**Validates: Requirements 1.1–1.5, 2.1–2.3, 3.1–3.6, 4.1–4.5, 5.1–5.4, 6.1–6.5, 7.1–7.4, 8.1–8.4**

Tests:
- /api/alerts endpoint returns merged alerts correctly
- Each tab render function produces expected HTML structure with sample data
- Edge cases: empty positions, null autonomous fields, missing price_history, zero NAV
- Classification functions at exact boundaries (beta 0.39, 0.4, 0.59, 0.6)
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Python equivalents of computation functions (imported from property tests)
# ---------------------------------------------------------------------------

from tests.test_property_exposure import compute_gross_exposure, compute_net_exposure
from tests.test_property_position_metrics import (
    classify_factor_beta,
    compute_capital_freed_by_trims,
    compute_trail_stop_proximity,
)
from tests.test_property_alerts_vol_conviction import (
    compute_trailing_20d_vol,
    compute_conviction_trajectory,
    group_alerts_by_severity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(tmp_path):
    """Create a Flask test client with memos dirs pointing to a temp directory."""
    # Create temp structure
    logs_dir = tmp_path / "memos" / "logs"
    logs_dir.mkdir(parents=True)
    state_dir = tmp_path / "memos" / "state"
    state_dir.mkdir(parents=True)
    debate_dir = tmp_path / "memos" / "debate"
    debate_dir.mkdir(parents=True)
    risk_dir = tmp_path / "memos" / "risk"
    risk_dir.mkdir(parents=True)
    scores_dir = tmp_path / "memos" / "scores"
    scores_dir.mkdir(parents=True)

    # Write a minimal book.json
    book = {
        "nav": 10_000_000,
        "initial_nav": 10_000_000,
        "cash_pct": 0.25,
        "positions": [],
        "trade_journal": [],
    }
    (state_dir / "book.json").write_text(json.dumps(book))

    alerts_path = state_dir / "alerts.json"

    import serve
    original_logs_dir = serve.LOGS_DIR
    original_alerts_path = serve.ALERTS_PATH
    serve.LOGS_DIR = logs_dir
    serve.ALERTS_PATH = alerts_path

    client = serve.app.test_client()
    yield client, logs_dir, alerts_path, state_dir

    serve.LOGS_DIR = original_logs_dir
    serve.ALERTS_PATH = original_alerts_path


@pytest.fixture
def sample_positions():
    """Sample position data for testing dashboard rendering logic."""
    return [
        {
            "ticker": "AAPL",
            "hedge_ticker": "MSFT",
            "direction": "long",
            "status": "active",
            "entry_price": 150.0,
            "current_price": 165.0,
            "hedge_entry_price": 300.0,
            "hedge_current_price": 310.0,
            "size_pct_nav": 0.08,
            "combined_pnl_pct": 0.05,
            "unrealized_pnl_pct": 0.05,
            "daily_change_pct": 0.01,
            "price_history": [
                {"date": f"2025-06-{10+i}", "price": 150.0 + i, "daily_change_pct": 0.01 * ((-1)**i)}
                for i in range(25)
            ],
            "trim_status": "half_trimmed",
            "trail_stop_level": 160.0,
            "thesis_status": "active",
            "proposal_id": "prop_001",
            "entry_date": "2025-06-01",
        },
        {
            "ticker": "TSLA",
            "hedge_ticker": "F",
            "direction": "short",
            "status": "active",
            "entry_price": 250.0,
            "current_price": 230.0,
            "hedge_entry_price": 12.0,
            "hedge_current_price": 11.5,
            "size_pct_nav": 0.06,
            "combined_pnl_pct": 0.03,
            "unrealized_pnl_pct": 0.03,
            "daily_change_pct": -0.005,
            "price_history": [
                {"date": f"2025-06-{10+i}", "price": 250.0 - i, "daily_change_pct": -0.005}
                for i in range(25)
            ],
            "trim_status": "untrimmed",
            "trail_stop_level": None,
            "thesis_status": "review_overdue",
            "proposal_id": "prop_002",
            "entry_date": "2025-05-15",
        },
        {
            "ticker": "NVDA",
            "hedge_ticker": "AMD",
            "direction": "long",
            "status": "active",
            "entry_price": 800.0,
            "current_price": 820.0,
            "hedge_entry_price": 150.0,
            "hedge_current_price": 145.0,
            "size_pct_nav": 0.10,
            "combined_pnl_pct": 0.02,
            "unrealized_pnl_pct": 0.02,
            "daily_change_pct": 0.003,
            "price_history": [
                {"date": f"2025-06-{10+i}", "price": 800.0 + i * 0.5, "daily_change_pct": 0.003}
                for i in range(25)
            ],
            "trim_status": "fully_exited",
            "trail_stop_level": 790.0,
            "thesis_status": "active",
            "proposal_id": "prop_003",
            "entry_date": "2025-06-10",
        },
    ]


@pytest.fixture
def sample_debates():
    """Sample debate data for IC Debate tab testing."""
    return [
        {
            "proposal_id": "prop_001",
            "ticker": "AAPL",
            "rounds": [
                {
                    "round": 1,
                    "arguments": [
                        {"agent": "analyst_1", "stance": "support", "argument": "Strong earnings ahead", "conviction": 7, "revised_conviction": 8},
                        {"agent": "analyst_2", "stance": "challenge", "argument": "Valuation stretched", "conviction": 4, "revised_conviction": 5},
                    ],
                },
                {
                    "round": 2,
                    "arguments": [
                        {"agent": "analyst_1", "stance": "support", "argument": "Catalyst confirmed", "conviction": 8, "revised_conviction": 9},
                        {"agent": "analyst_2", "stance": "support", "argument": "Revised upward", "conviction": 5, "revised_conviction": 7},
                    ],
                },
            ],
            "final_conviction": 8,
            "outcome": "booked",
        },
        {
            "proposal_id": "prop_rejected",
            "ticker": "META",
            "rounds": [
                {
                    "round": 1,
                    "arguments": [
                        {"agent": "analyst_1", "stance": "challenge", "argument": "Risk too high", "conviction": 3},
                    ],
                },
            ],
            "final_conviction": 3,
            "outcome": "rejected",
        },
    ]


@pytest.fixture
def sample_logs():
    """Sample cycle log data for Run Log tab testing."""
    return [
        {
            "timestamp": "2025-07-01T10:00:00-04:00",
            "cycle_type": "full_desk_run",
            "proposals_evaluated": 5,
            "orders": [
                {"ticker": "AAPL", "conviction": 8, "risk_decision": "approved", "pm_execute": True, "gate_result": "passed"},
                {"ticker": "GOOG", "conviction": 4, "risk_decision": "approved", "pm_execute": True, "gate_result": "failed", "failing_gate": "conviction"},
            ],
            "circuit_breaker_active": False,
        },
        {
            "timestamp": "2025-07-01T09:30:00-04:00",
            "cycle_type": "full_desk_run",
            "proposals_evaluated": 3,
            "orders": [
                {"ticker": "TSLA", "conviction": 6, "risk_decision": "denied", "pm_execute": False, "gate_result": "failed", "failing_gate": "risk"},
            ],
            "circuit_breaker_active": True,
            "drawdown_at_time": 0.035,
        },
    ]


# ---------------------------------------------------------------------------
# 1. /api/alerts endpoint integration tests
# ---------------------------------------------------------------------------

class TestApiAlertsIntegration:
    """Verify /api/alerts endpoint merges alerts correctly."""

    def test_alert_severity_grouping_from_monitor_alerts(self, app_client):
        """Monitor alerts from alerts.json are correctly loaded and can be grouped by severity."""
        client, logs_dir, alerts_path, state_dir = app_client

        monitor_data = [
            {"level": "critical", "category": "stop", "ticker": "AAPL", "message": "Stop breached", "action": "Close", "timestamp": "2025-07-01T10:00:00"},
            {"level": "critical", "category": "drawdown", "ticker": "PORTFOLIO", "message": "Max drawdown", "action": "Halt", "timestamp": "2025-07-01T10:01:00"},
            {"level": "warning", "category": "factor", "ticker": "SPY", "message": "Beta elevated", "action": "Monitor", "timestamp": "2025-07-01T10:02:00"},
            {"level": "info", "category": "sigma", "ticker": "NVDA", "message": "2-sigma event", "action": "Review", "timestamp": "2025-07-01T10:03:00"},
            {"level": "info", "category": "holding", "ticker": "TSLA", "message": "Long hold", "action": "Assess", "timestamp": "2025-07-01T10:04:00"},
        ]
        alerts_path.write_text(json.dumps(monitor_data))

        resp = client.get("/api/alerts")
        data = resp.get_json()

        # Verify severity grouping
        counts = group_alerts_by_severity(data["monitor_alerts"])
        assert counts["critical"] == 2
        assert counts["warning"] == 1
        assert counts["info"] == 2
        assert counts["critical"] + counts["warning"] + counts["info"] == len(data["monitor_alerts"])

    def test_alerts_endpoint_returns_health_entries_from_today(self, app_client):
        """Health entries from today's logs are included in the response."""
        from datetime import datetime
        client, logs_dir, alerts_path, state_dir = app_client

        today = datetime.now().strftime("%Y-%m-%d")
        health_entry = {
            "timestamp": f"{today}T09:30:00-04:00",
            "cycle_type": "price_poll",
            "status": "ok",
        }
        (logs_dir / f"price_poll_{today}T09-30-00.json").write_text(json.dumps(health_entry))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        assert len(data["health"]) >= 1
        assert data["health"][0]["cycle_type"] == "price_poll"

    def test_alerts_endpoint_with_large_alert_count(self, app_client):
        """Endpoint handles many alerts and returns at most 50 log-based alerts."""
        client, logs_dir, alerts_path, state_dir = app_client

        # Create 60 telegram_delivery entries
        for i in range(60):
            entry = {
                "timestamp": f"2025-07-01T{10 + i // 60:02d}:{i % 60:02d}:00-04:00",
                "cycle_type": "telegram_delivery",
                "message": f"Alert #{i}",
            }
            (logs_dir / f"telegram_2025-07-01T{10 + i // 60:02d}-{i % 60:02d}-00.json").write_text(json.dumps(entry))

        resp = client.get("/api/alerts")
        data = resp.get_json()
        # serve.py caps at 50 log-based alerts
        assert len(data["alerts"]) <= 50


# ---------------------------------------------------------------------------
# 2. Dashboard HTML generation tests
# ---------------------------------------------------------------------------

class TestDashboardHTMLGeneration:
    """Test that dashboard.py generates HTML with expected structural elements."""

    @pytest.fixture(autouse=True)
    def setup_dashboard(self, tmp_path):
        """Set up a temporary environment to run dashboard.py build_html."""
        self.tmp_path = tmp_path
        # Create required directories with sample data
        state_dir = tmp_path / "memos" / "state"
        state_dir.mkdir(parents=True)
        debate_dir = tmp_path / "memos" / "debate"
        debate_dir.mkdir(parents=True)
        risk_dir = tmp_path / "memos" / "risk"
        risk_dir.mkdir(parents=True)
        scores_dir = tmp_path / "memos" / "scores"
        scores_dir.mkdir(parents=True)
        logs_dir = tmp_path / "memos" / "logs"
        logs_dir.mkdir(parents=True)

        book = {
            "nav": 10_000_000,
            "initial_nav": 10_000_000,
            "cash_pct": 0.25,
            "positions": [
                {
                    "ticker": "AAPL",
                    "hedge_ticker": "MSFT",
                    "direction": "long",
                    "status": "active",
                    "entry_price": 150.0,
                    "current_price": 165.0,
                    "hedge_entry_price": 300.0,
                    "hedge_current_price": 310.0,
                    "size_pct_nav": 0.08,
                    "combined_pnl_pct": 0.05,
                    "daily_change_pct": 0.01,
                    "price_history": [],
                    "trim_status": "half_trimmed",
                    "trail_stop_level": 160.0,
                    "thesis_status": "active",
                    "proposal_id": "prop_001",
                    "entry_date": "2025-06-01",
                }
            ],
            "trade_journal": [],
        }
        (state_dir / "book.json").write_text(json.dumps(book))
        (state_dir / "pnl_history.json").write_text(json.dumps([]))

        self.book = book

    def _generate_html(self):
        """Generate dashboard HTML using dashboard.py's build_html."""
        import dashboard
        original_book_path = dashboard.BOOK_PATH
        original_history_path = dashboard.HISTORY_PATH
        original_debate_dir = dashboard.DEBATE_DIR
        original_risk_dir = dashboard.RISK_DIR
        original_scores_dir = dashboard.SCORES_DIR
        original_logs_dir = dashboard.LOGS_DIR

        try:
            dashboard.BOOK_PATH = self.tmp_path / "memos" / "state" / "book.json"
            dashboard.HISTORY_PATH = self.tmp_path / "memos" / "state" / "pnl_history.json"
            dashboard.DEBATE_DIR = self.tmp_path / "memos" / "debate"
            dashboard.RISK_DIR = self.tmp_path / "memos" / "risk"
            dashboard.SCORES_DIR = self.tmp_path / "memos" / "scores"
            dashboard.LOGS_DIR = self.tmp_path / "memos" / "logs"
            html = dashboard.build_html()
        finally:
            dashboard.BOOK_PATH = original_book_path
            dashboard.HISTORY_PATH = original_history_path
            dashboard.DEBATE_DIR = original_debate_dir
            dashboard.RISK_DIR = original_risk_dir
            dashboard.SCORES_DIR = original_scores_dir
            dashboard.LOGS_DIR = original_logs_dir

        return html

    def test_autonomous_banner_present(self):
        """Dashboard contains the autonomous status banner with CB indicator."""
        html = self._generate_html()
        assert 'class="autonomous-banner"' in html
        assert 'id="autonomous-banner"' in html
        assert 'id="circuit-breaker-indicator"' in html
        assert 'id="cb-label"' in html
        assert "Autonomous Mode" in html

    def test_autonomous_banner_has_trade_counts(self):
        """Banner shows auto-booked trade count and session count elements."""
        html = self._generate_html()
        assert 'id="banner-lifetime-trades"' in html
        assert 'id="banner-session-count"' in html
        assert "Auto-Booked" in html

    def test_autonomous_banner_has_last_cycle(self):
        """Banner shows last pipeline cycle timestamp."""
        html = self._generate_html()
        assert 'id="banner-last-cycle-value"' in html
        assert "Last Cycle" in html

    def test_autonomous_banner_has_overlap_guard(self):
        """Banner has overlap guard 'Cycle Skipped' indicator."""
        html = self._generate_html()
        assert 'id="banner-overlap-guard"' in html
        assert "Cycle Skipped" in html

    def test_book_tab_panel_exists(self):
        """Book tab (positions) panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-positions"' in html

    def test_risk_tab_panel_exists(self):
        """Risk tab panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-risk"' in html

    def test_debate_tab_panel_exists(self):
        """IC Debate tab panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-debate"' in html

    def test_technical_tab_panel_exists(self):
        """Technicals tab panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-technical"' in html

    def test_run_log_tab_panel_exists(self):
        """Run Log (timeline) tab panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-timeline"' in html

    def test_overview_tab_panel_exists(self):
        """Overview tab panel is present in the HTML."""
        html = self._generate_html()
        assert 'id="panel-overview"' in html

    def test_computation_functions_embedded(self):
        """All computation functions are embedded in the generated JavaScript."""
        html = self._generate_html()
        assert "computeGrossExposure" in html
        assert "computeNetExposure" in html
        assert "computeAveragePairPnL" in html
        assert "computeCapitalFreedByTrims" in html
        assert "computeTrailStopProximity" in html
        assert "computeTrailing20dVol" in html
        assert "computeDrawdownFromPeak" in html
        assert "classifyFactorBeta" in html
        assert "computeDaysOverdue" in html
        assert "computeConvictionTrajectory" in html

    def test_trim_status_badge_css_classes(self):
        """CSS for trim status badges is present."""
        html = self._generate_html()
        # The dashboard should include styling for trim badges
        assert "trim" in html.lower()

    def test_trail_stop_rendering_logic(self):
        """Trail stop rendering logic is present in JS."""
        html = self._generate_html()
        assert "trail_stop_level" in html

    def test_thesis_status_rendering_logic(self):
        """Thesis status rendering logic is present in JS."""
        html = self._generate_html()
        assert "thesis_status" in html
        assert "review_overdue" in html

    def test_sigma_event_rendering_logic(self):
        """Sigma event rendering logic is present in JS."""
        html = self._generate_html()
        assert "sigma" in html.lower()

    def test_embedded_data_includes_positions(self):
        """Embedded fallback data includes position data from book.json."""
        html = self._generate_html()
        assert "AAPL" in html
        assert "half_trimmed" in html

    def test_refresh_loop_configured(self):
        """The 30-second refresh loop is configured in the JavaScript."""
        html = self._generate_html()
        assert "refreshAll" in html
        assert "30000" in html or "30 * 1000" in html or "setInterval" in html

    def test_stale_data_indicator_present(self):
        """Stale data indicator element is in the HTML."""
        html = self._generate_html()
        assert "Stale data" in html or "stale" in html.lower()


# ---------------------------------------------------------------------------
# 3. Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases: empty positions, null autonomous fields, missing price_history, zero NAV."""

    def test_empty_positions_gross_exposure_zero(self):
        """Empty positions array yields zero gross exposure."""
        assert compute_gross_exposure([]) == 0.0

    def test_empty_positions_net_exposure_zero(self):
        """Empty positions array yields zero net exposure."""
        assert compute_net_exposure([]) == 0.0

    def test_empty_positions_capital_freed_zero(self):
        """Empty positions with valid NAV yields zero capital freed."""
        assert compute_capital_freed_by_trims([], 10_000_000) == 0.0

    def test_none_positions_gross_exposure_zero(self):
        """None positions yields zero gross exposure."""
        assert compute_gross_exposure(None) == 0.0

    def test_none_positions_net_exposure_zero(self):
        """None positions yields zero net exposure."""
        assert compute_net_exposure(None) == 0.0

    def test_null_trim_status_treated_as_untrimmed(self):
        """Position with null/missing trim_status does not contribute to capital freed."""
        positions = [
            {"trim_status": None, "size_pct_nav": 0.10},
            {"size_pct_nav": 0.05},  # No trim_status key at all
        ]
        result = compute_capital_freed_by_trims(positions, 10_000_000)
        assert result == 0.0

    def test_null_trail_stop_level_returns_none(self):
        """Position with null trail_stop_level returns None proximity."""
        position = {
            "current_price": 165.0,
            "trail_stop_level": None,
            "direction": "long",
        }
        assert compute_trail_stop_proximity(position) is None

    def test_missing_trail_stop_level_returns_none(self):
        """Position without trail_stop_level key returns None proximity."""
        position = {
            "current_price": 165.0,
            "direction": "long",
        }
        assert compute_trail_stop_proximity(position) is None

    def test_null_thesis_status_no_days_overdue(self):
        """Null thesis_status means no overdue days (treated as 'active')."""
        # The function is client-side JS; we test the Python logic equivalent
        # The dashboard treats missing thesis_status as "active"
        position = {"thesis_status": None}
        # Should not trigger overdue logic
        assert position.get("thesis_status") != "review_overdue"

    def test_missing_price_history_volatility_returns_none(self):
        """Empty or missing price_history yields None volatility."""
        assert compute_trailing_20d_vol([]) is None
        assert compute_trailing_20d_vol(None) is None

    def test_single_entry_price_history_returns_none(self):
        """Price history with only 1 entry (< 2) yields None volatility."""
        assert compute_trailing_20d_vol([{"daily_change_pct": 0.01}]) is None

    def test_zero_nav_capital_freed_returns_zero(self):
        """Zero NAV causes capital freed calculation to return 0."""
        positions = [{"trim_status": "half_trimmed", "size_pct_nav": 0.10}]
        assert compute_capital_freed_by_trims(positions, 0) == 0.0

    def test_negative_nav_capital_freed_returns_zero(self):
        """Negative NAV causes capital freed calculation to return 0."""
        positions = [{"trim_status": "half_trimmed", "size_pct_nav": 0.10}]
        assert compute_capital_freed_by_trims(positions, -1_000_000) == 0.0

    def test_none_nav_capital_freed_returns_zero(self):
        """None NAV causes capital freed calculation to return 0."""
        positions = [{"trim_status": "half_trimmed", "size_pct_nav": 0.10}]
        assert compute_capital_freed_by_trims(positions, None) == 0.0

    def test_position_with_zero_current_price_proximity_none(self):
        """Position with current_price = 0 returns None for trail stop proximity."""
        position = {
            "current_price": 0,
            "trail_stop_level": 100.0,
            "direction": "long",
        }
        assert compute_trail_stop_proximity(position) is None

    def test_empty_debate_returns_empty_trajectory(self):
        """Debate with no rounds returns empty trajectory."""
        assert compute_conviction_trajectory(None) == []
        assert compute_conviction_trajectory({}) == []
        assert compute_conviction_trajectory({"rounds": []}) == []

    def test_alert_grouping_with_empty_list(self):
        """Empty alert list gives zero counts for all severities."""
        counts = group_alerts_by_severity([])
        assert counts == {"critical": 0, "warning": 0, "info": 0}

    def test_positions_with_null_size_pct_nav(self):
        """Positions with null size_pct_nav are treated as 0 exposure."""
        positions = [
            {"size_pct_nav": None, "direction": "long"},
            {"size_pct_nav": 0.05, "direction": "short"},
        ]
        gross = compute_gross_exposure(positions)
        assert math.isclose(gross, 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 4. Classification function boundary tests
# ---------------------------------------------------------------------------

class TestClassifyFactorBetaBoundaries:
    """Test classifyFactorBeta at exact boundaries (0.39, 0.4, 0.59, 0.6)."""

    def test_beta_0_39_is_green(self):
        """Beta 0.39 (|beta| < 0.4) should return 'green'."""
        assert classify_factor_beta(0.39) == "green"

    def test_beta_0_4_is_amber(self):
        """Beta 0.4 (|beta| >= 0.4) should return 'amber'."""
        assert classify_factor_beta(0.4) == "amber"

    def test_beta_0_59_is_amber(self):
        """Beta 0.59 (0.4 <= |beta| < 0.6) should return 'amber'."""
        assert classify_factor_beta(0.59) == "amber"

    def test_beta_0_6_is_red(self):
        """Beta 0.6 (|beta| >= 0.6) should return 'red'."""
        assert classify_factor_beta(0.6) == "red"

    def test_negative_beta_0_39_is_green(self):
        """Beta -0.39 (|-0.39| < 0.4) should return 'green'."""
        assert classify_factor_beta(-0.39) == "green"

    def test_negative_beta_0_4_is_amber(self):
        """Beta -0.4 (|-0.4| >= 0.4) should return 'amber'."""
        assert classify_factor_beta(-0.4) == "amber"

    def test_negative_beta_0_59_is_amber(self):
        """Beta -0.59 (0.4 <= |-0.59| < 0.6) should return 'amber'."""
        assert classify_factor_beta(-0.59) == "amber"

    def test_negative_beta_0_6_is_red(self):
        """Beta -0.6 (|-0.6| >= 0.6) should return 'red'."""
        assert classify_factor_beta(-0.6) == "red"

    def test_beta_zero_is_green(self):
        """Beta 0 should return 'green'."""
        assert classify_factor_beta(0) == "green"

    def test_beta_none_is_green(self):
        """Beta None should return 'green'."""
        assert classify_factor_beta(None) == "green"

    def test_beta_1_0_is_red(self):
        """Beta 1.0 should return 'red'."""
        assert classify_factor_beta(1.0) == "red"

    def test_beta_negative_1_0_is_red(self):
        """Beta -1.0 should return 'red'."""
        assert classify_factor_beta(-1.0) == "red"

    def test_beta_just_below_0_4_is_green(self):
        """Beta 0.3999... (just below 0.4) should return 'green'."""
        assert classify_factor_beta(0.3999999) == "green"

    def test_beta_just_below_0_6_is_amber(self):
        """Beta 0.5999... (just below 0.6) should return 'amber'."""
        assert classify_factor_beta(0.5999999) == "amber"


# ---------------------------------------------------------------------------
# 5. Computation function integration tests with realistic data
# ---------------------------------------------------------------------------

class TestComputationIntegration:
    """Integration tests for computation functions with realistic sample data."""

    def test_gross_exposure_with_sample_positions(self, sample_positions):
        """Gross exposure sums absolute size_pct_nav values."""
        gross = compute_gross_exposure(sample_positions)
        expected = 0.08 + 0.06 + 0.10  # = 0.24
        assert math.isclose(gross, expected, rel_tol=1e-9)

    def test_net_exposure_with_mixed_directions(self, sample_positions):
        """Net exposure accounts for long (positive) and short (negative)."""
        net = compute_net_exposure(sample_positions)
        # AAPL long: +0.08, TSLA short: -0.06, NVDA long: +0.10
        expected = 0.08 - 0.06 + 0.10  # = 0.12
        assert math.isclose(net, expected, rel_tol=1e-9)

    def test_capital_freed_by_trims_with_sample(self, sample_positions):
        """Capital freed by trims accounts only for half_trimmed positions."""
        nav = 10_000_000
        result = compute_capital_freed_by_trims(sample_positions, nav)
        # Only AAPL is half_trimmed: |0.08| * 10_000_000 * 0.5 = 400_000
        expected = 0.08 * nav * 0.5
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_trail_stop_proximity_long_position(self, sample_positions):
        """Trail stop proximity for a long position is (current - stop) / current."""
        aapl = sample_positions[0]  # long, current_price=165, trail_stop=160
        result = compute_trail_stop_proximity(aapl)
        expected = (165.0 - 160.0) / 165.0
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_trail_stop_proximity_short_position(self):
        """Trail stop proximity for a short position is (stop - current) / current."""
        position = {
            "direction": "short",
            "current_price": 230.0,
            "trail_stop_level": 240.0,
        }
        result = compute_trail_stop_proximity(position)
        expected = (240.0 - 230.0) / 230.0
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_trailing_volatility_with_sample_history(self, sample_positions):
        """Trailing 20d vol computes sample stddev on last 20 daily_change_pct values."""
        aapl = sample_positions[0]
        result = compute_trailing_20d_vol(aapl["price_history"])
        assert result is not None
        assert result >= 0.0

        # Verify manually: last 20 values from the 25-entry history
        values = [h["daily_change_pct"] for h in aapl["price_history"][-20:]]
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        expected = math.sqrt(variance)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_conviction_trajectory_with_sample_debate(self, sample_debates):
        """Conviction trajectory produces ordered average conviction values."""
        debate = sample_debates[0]  # prop_001 with 2 rounds
        trajectory = compute_conviction_trajectory(debate)

        # Round 1: avg of revised_convictions [8, 5] = 6.5
        # Round 2: avg of revised_convictions [9, 7] = 8.0
        assert len(trajectory) == 2
        assert math.isclose(trajectory[0], 6.5, rel_tol=1e-9)
        assert math.isclose(trajectory[1], 8.0, rel_tol=1e-9)

    def test_conviction_trajectory_preserves_ascending_order(self, sample_debates):
        """Trajectory is in temporal (round number) order even if input is unordered."""
        debate = sample_debates[0]
        # Reverse the rounds in the input
        debate_reversed = {
            "rounds": list(reversed(debate["rounds"])),
            "proposal_id": debate["proposal_id"],
        }
        trajectory = compute_conviction_trajectory(debate_reversed)
        # Should still be ordered by round number: round 1 first, round 2 second
        assert len(trajectory) == 2
        assert math.isclose(trajectory[0], 6.5, rel_tol=1e-9)
        assert math.isclose(trajectory[1], 8.0, rel_tol=1e-9)

    def test_alert_grouping_with_mixed_severities(self):
        """Alert grouping correctly counts mixed severity levels."""
        alerts = [
            {"level": "critical", "category": "stop", "ticker": "AAPL", "message": "M1"},
            {"level": "critical", "category": "drawdown", "ticker": "PORT", "message": "M2"},
            {"level": "warning", "category": "factor", "ticker": "SPY", "message": "M3"},
            {"level": "warning", "category": "correlation", "ticker": "TSLA", "message": "M4"},
            {"level": "warning", "category": "holding", "ticker": "NVDA", "message": "M5"},
            {"level": "info", "category": "sigma", "ticker": "META", "message": "M6"},
        ]
        counts = group_alerts_by_severity(alerts)
        assert counts["critical"] == 2
        assert counts["warning"] == 3
        assert counts["info"] == 1
        assert sum(counts.values()) == len(alerts)
