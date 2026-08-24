"""
Unit tests for enhanced auto_close_stopped_positions (Task 5.4, Task 3.3).

Validates:
  - Slippage-adjusted exit prices via compute_fill_price
  - trim_status transitions to 'fully_exited'
  - cash_pct restored by 2 × size_pct_nav
  - Critical alert appended with ticker, exit_price, loss amount
  - Trade journal entries include exit_reason="stop_breach" and realized_pnl_pct
  - Fetch-failed ticker guard: skip stop execution and emit WARNING alert

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date
from unittest.mock import patch, MagicMock

# We need to mock PriceService before importing monitor
with patch.dict("sys.modules", {"data_platform.prices": type(sys)("mock_prices")}):
    # Create a mock PriceService class that returns a mock instance with get_fetch_status
    mock_mod = sys.modules["data_platform.prices"]

    class MockPriceService:
        def __init__(self):
            self.fetch_status = {}

        def get_fetch_status(self, ticker: str) -> str:
            return self.fetch_status.get(ticker, "ok")

    mock_mod.PriceService = MockPriceService

    # Now import the function under test
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from monitor import auto_close_stopped_positions, Alert
    import monitor as _monitor_module


def make_book(positions=None, cash_pct=0.70, nav=10_000_000):
    """Create a test book with sensible defaults."""
    return {
        "nav": nav,
        "cash_pct": cash_pct,
        "positions": positions or [],
        "trade_journal": [],
    }


def make_position(
    ticker="AAPL",
    status="active",
    stop_triggered=True,
    current_price=150.0,
    combined_pnl_pct=-0.035,
    direction="long",
    size_pct_nav=0.03,
    trim_status="untrimmed",
):
    return {
        "ticker": ticker,
        "status": status,
        "stop_triggered": stop_triggered,
        "current_price": current_price,
        "combined_pnl_pct": combined_pnl_pct,
        "direction": direction,
        "size_pct_nav": size_pct_nav,
        "trim_status": trim_status,
    }


class TestAutoCloseSlippageAdjustedExit:
    """Verify slippage-adjusted exit prices are used (Requirement 3.1)."""

    def test_long_exit_receives_less_than_current_price(self):
        pos = make_position(direction="long", current_price=100.0)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        # Long exit: price × (1 - bps/10000) → less than current
        assert pos["exit_price"] < 100.0
        # With default 5bps: 100 * (1 - 5/10000) = 99.95
        assert abs(pos["exit_price"] - 99.95) < 0.001

    def test_short_exit_pays_more_than_current_price(self):
        pos = make_position(direction="short", current_price=100.0)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        # Short exit: price × (1 + bps/10000) → more than current
        assert pos["exit_price"] > 100.0
        # With default 5bps: 100 * (1 + 5/10000) = 100.05
        assert abs(pos["exit_price"] - 100.05) < 0.001

    def test_none_current_price_handled_gracefully(self):
        pos = make_position(current_price=None)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["exit_price"] is None
        assert pos["status"] == "closed"


class TestAutoCloseTrimStatus:
    """Verify trim_status transitions to 'fully_exited' (Requirement 3.1)."""

    def test_untrimmed_transitions_to_fully_exited(self):
        pos = make_position(trim_status="untrimmed")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["trim_status"] == "fully_exited"

    def test_half_trimmed_transitions_to_fully_exited(self):
        pos = make_position(trim_status="half_trimmed")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["trim_status"] == "fully_exited"

    def test_already_fully_exited_remains_fully_exited(self):
        # Edge case: position somehow already fully_exited but still active
        pos = make_position(trim_status="fully_exited")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["trim_status"] == "fully_exited"


class TestAutoCloseCashRestoration:
    """Verify cash_pct is restored by 2 × size_pct_nav (Requirement 3.1)."""

    def test_cash_restored_by_2x_size(self):
        pos = make_position(size_pct_nav=0.03)
        book = make_book(positions=[pos], cash_pct=0.70)
        alerts = []

        auto_close_stopped_positions(book, alerts)

        # Should restore 0.03 * 2 = 0.06
        assert abs(book["cash_pct"] - 0.76) < 1e-10

    def test_multiple_closures_restore_all_cash(self):
        pos1 = make_position(ticker="AAPL", size_pct_nav=0.03)
        pos2 = make_position(ticker="MSFT", size_pct_nav=0.04)
        book = make_book(positions=[pos1, pos2], cash_pct=0.50)
        alerts = []

        auto_close_stopped_positions(book, alerts)

        # 0.50 + (0.03 * 2) + (0.04 * 2) = 0.50 + 0.06 + 0.08 = 0.64
        assert abs(book["cash_pct"] - 0.64) < 1e-10


class TestAutoCloseTradeJournal:
    """Verify trade journal entries (Requirement 3.2)."""

    def test_journal_entry_has_exit_reason(self):
        pos = make_position()
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert len(book["trade_journal"]) == 1
        entry = book["trade_journal"][0]
        assert entry["exit_reason"] == "stop_breach"

    def test_journal_entry_has_realized_pnl_pct(self):
        pos = make_position(combined_pnl_pct=-0.04)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        entry = book["trade_journal"][0]
        assert entry["realized_pnl_pct"] == -0.04

    def test_journal_entry_has_slippage_adjusted_exit_price(self):
        pos = make_position(current_price=200.0, direction="long")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        entry = book["trade_journal"][0]
        # Long exit with 5bps slippage: 200 * (1 - 5/10000) = 199.90
        assert abs(entry["exit_price"] - 199.90) < 0.01

    def test_journal_entry_has_ticker_and_timestamp(self):
        pos = make_position(ticker="GOOG")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        entry = book["trade_journal"][0]
        assert entry["ticker"] == "GOOG"
        assert "timestamp" in entry


class TestAutoCloseAlerts:
    """Verify critical alert is appended (Requirement 3.3)."""

    def test_critical_alert_appended(self):
        pos = make_position(ticker="TSLA", current_price=250.0, combined_pnl_pct=-0.03)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.level == "critical"
        assert alert.category == "stop"
        assert alert.ticker == "TSLA"

    def test_alert_contains_exit_price(self):
        pos = make_position(ticker="TSLA", current_price=250.0, direction="long")
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        alert = alerts[0]
        # Exit price for long: 250 * (1 - 5/10000) = 249.875
        assert "$249.88" in alert.message or "$249.87" in alert.message

    def test_alert_contains_loss_amount(self):
        pos = make_position(
            ticker="TSLA",
            current_price=250.0,
            combined_pnl_pct=-0.03,
            size_pct_nav=0.03,
        )
        book = make_book(positions=[pos], nav=10_000_000)
        alerts = []

        auto_close_stopped_positions(book, alerts)

        alert = alerts[0]
        # Loss: -0.03 * 0.03 * 10_000_000 = -9000
        assert "9,000" in alert.action


class TestAutoCloseSkipsNonTriggered:
    """Verify only stop-triggered active positions are closed."""

    def test_non_active_positions_skipped(self):
        pos = make_position(status="closed", stop_triggered=True)
        book = make_book(positions=[pos], cash_pct=0.70)
        alerts = []

        result = auto_close_stopped_positions(book, alerts)

        assert result == 0
        assert book["cash_pct"] == 0.70

    def test_non_triggered_positions_skipped(self):
        pos = make_position(stop_triggered=False)
        book = make_book(positions=[pos], cash_pct=0.70)
        alerts = []

        result = auto_close_stopped_positions(book, alerts)

        assert result == 0
        assert book["cash_pct"] == 0.70

    def test_returns_closed_count(self):
        pos1 = make_position(ticker="AAPL")
        pos2 = make_position(ticker="MSFT")
        pos3 = make_position(ticker="SKIP", stop_triggered=False)
        book = make_book(positions=[pos1, pos2, pos3])
        alerts = []

        result = auto_close_stopped_positions(book, alerts)

        assert result == 2


class TestAutoClosePositionFields:
    """Verify position fields are set correctly on close."""

    def test_position_status_set_to_closed(self):
        pos = make_position()
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["status"] == "closed"

    def test_exit_date_is_today(self):
        pos = make_position()
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["exit_date"] == date.today().isoformat()

    def test_exit_reason_is_stop_breach(self):
        pos = make_position()
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["exit_reason"] == "stop_breach"

    def test_realized_pnl_pct_matches_combined(self):
        pos = make_position(combined_pnl_pct=-0.027)
        book = make_book(positions=[pos])
        alerts = []

        auto_close_stopped_positions(book, alerts)

        assert pos["realized_pnl_pct"] == -0.027


class TestAutoCloseFetchFailedGuard:
    """Verify stop execution is skipped when ticker is fetch_failed (Requirement 8.4)."""

    def test_fetch_failed_skips_stop_execution(self):
        """Stop execution is skipped when price data is unavailable."""
        pos = make_position(ticker="BADTICKER")
        book = make_book(positions=[pos], cash_pct=0.70)
        alerts = []

        # Set the ticker as fetch_failed in the module-level price_service
        _monitor_module.price_service.fetch_status["BADTICKER"] = "fetch_failed"

        try:
            result = auto_close_stopped_positions(book, alerts)

            # Position should NOT be closed
            assert pos["status"] == "active"
            assert result == 0
            assert book["cash_pct"] == 0.70
            assert len(book["trade_journal"]) == 0
        finally:
            _monitor_module.price_service.fetch_status.pop("BADTICKER", None)

    def test_fetch_failed_emits_warning_alert(self):
        """A WARNING alert is emitted when stop is skipped due to fetch_failed."""
        pos = make_position(ticker="BADTICKER")
        book = make_book(positions=[pos])
        alerts = []

        _monitor_module.price_service.fetch_status["BADTICKER"] = "fetch_failed"

        try:
            auto_close_stopped_positions(book, alerts)

            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.level == "warning"
            assert alert.category == "stop"
            assert alert.ticker == "BADTICKER"
            assert "fetch_failed" in alert.message
        finally:
            _monitor_module.price_service.fetch_status.pop("BADTICKER", None)

    def test_fetch_failed_clears_stop_triggered_flag(self):
        """stop_triggered is cleared so it can be re-evaluated next cycle."""
        pos = make_position(ticker="BADTICKER")
        book = make_book(positions=[pos])
        alerts = []

        _monitor_module.price_service.fetch_status["BADTICKER"] = "fetch_failed"

        try:
            auto_close_stopped_positions(book, alerts)

            assert pos["stop_triggered"] is False
        finally:
            _monitor_module.price_service.fetch_status.pop("BADTICKER", None)

    def test_fetch_ok_still_closes_position(self):
        """Normal positions (fetch status ok) are still closed."""
        pos = make_position(ticker="AAPL")
        book = make_book(positions=[pos])
        alerts = []

        # Ensure AAPL has default "ok" status (no explicit entry needed)
        result = auto_close_stopped_positions(book, alerts)

        assert pos["status"] == "closed"
        assert result == 1

    def test_mixed_fetch_failed_and_ok(self):
        """Only fetch_failed positions are skipped; others still close."""
        pos_bad = make_position(ticker="BADTICKER")
        pos_good = make_position(ticker="GOODTICKER")
        book = make_book(positions=[pos_bad, pos_good], cash_pct=0.50)
        alerts = []

        _monitor_module.price_service.fetch_status["BADTICKER"] = "fetch_failed"

        try:
            result = auto_close_stopped_positions(book, alerts)

            # Only the good ticker should be closed
            assert result == 1
            assert pos_bad["status"] == "active"
            assert pos_good["status"] == "closed"
            # One warning for BADTICKER, one critical for GOODTICKER
            assert len(alerts) == 2
            warning_alerts = [a for a in alerts if a.level == "warning"]
            critical_alerts = [a for a in alerts if a.level == "critical"]
            assert len(warning_alerts) == 1
            assert len(critical_alerts) == 1
            assert warning_alerts[0].ticker == "BADTICKER"
            assert critical_alerts[0].ticker == "GOODTICKER"
        finally:
            _monitor_module.price_service.fetch_status.pop("BADTICKER", None)
