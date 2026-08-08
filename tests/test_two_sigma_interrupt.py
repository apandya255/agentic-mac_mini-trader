"""
Unit tests for Two-Sigma Interrupt Detection (Task 3.4).

Validates that the price poller correctly detects when a position's single-day
move exceeds 2x the 90-day trailing standard deviation, fetches headlines,
and queues Telegram alerts.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**
"""

import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.price_poller import (
    _fetch_headlines_for_ticker,
    _get_position_tickers,
    handle_two_sigma_interrupts,
    _two_sigma_fired_today,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_book(positions):
    """Helper to create a book dict with given positions."""
    return {"positions": positions}


def make_position(ticker, hedge_ticker=None, status="active"):
    """Helper to create a position dict."""
    pos = {
        "ticker": ticker,
        "status": status,
        "entry_price": 100.0,
        "direction": "long",
    }
    if hedge_ticker:
        pos["hedge_ticker"] = hedge_ticker
    return pos


def make_daily_returns(n_days=95, std_dev=0.01, last_return=None):
    """
    Create a pd.Series of daily returns with a controlled std dev.

    Args:
        n_days: Number of return data points.
        std_dev: Standard deviation of the returns.
        last_return: If set, override the last return value.
    """
    rng = np.random.default_rng(42)
    returns = rng.normal(0, std_dev, n_days)
    if last_return is not None:
        returns[-1] = last_return
    index = pd.date_range(end=date.today(), periods=n_days, freq="B")
    return pd.Series(returns, index=index, name="XOM")


# ---------------------------------------------------------------------------
# Tests: _get_position_tickers
# ---------------------------------------------------------------------------


class TestGetPositionTickers:
    def test_extracts_primary_tickers(self):
        book = make_book([
            make_position("XOM"),
            make_position("AAPL"),
        ])
        tickers = _get_position_tickers(book)
        assert "XOM" in tickers
        assert "AAPL" in tickers

    def test_extracts_hedge_tickers(self):
        book = make_book([make_position("XLE", hedge_ticker="RSP")])
        tickers = _get_position_tickers(book)
        assert "XLE" in tickers
        assert "RSP" in tickers

    def test_ignores_closed_positions(self):
        book = make_book([
            make_position("XOM", status="active"),
            make_position("AAPL", status="closed"),
        ])
        tickers = _get_position_tickers(book)
        assert "XOM" in tickers
        assert "AAPL" not in tickers

    def test_empty_book(self):
        book = make_book([])
        tickers = _get_position_tickers(book)
        assert tickers == []


# ---------------------------------------------------------------------------
# Tests: _fetch_headlines_for_ticker
# ---------------------------------------------------------------------------


class TestFetchHeadlines:
    @patch("scripts.price_poller.logger")
    def test_returns_headline_when_available(self, mock_logger):
        mock_headline = MagicMock()
        mock_headline.title = "XOM beats earnings estimates"

        with patch("src.data_platform.news.NewsScanner") as MockScanner:
            instance = MockScanner.return_value
            instance.get_headlines.return_value = [mock_headline]

            result = _fetch_headlines_for_ticker("XOM")
            assert result == "XOM beats earnings estimates"

    @patch("scripts.price_poller.logger")
    def test_returns_no_visible_catalyst_when_empty(self, mock_logger):
        with patch("src.data_platform.news.NewsScanner") as MockScanner:
            instance = MockScanner.return_value
            instance.get_headlines.return_value = []

            result = _fetch_headlines_for_ticker("XOM")
            assert result == "no visible catalyst"

    @patch("scripts.price_poller.logger")
    def test_returns_unavailable_on_exception(self, mock_logger):
        with patch("src.data_platform.news.NewsScanner") as MockScanner:
            MockScanner.side_effect = ImportError("Module not available")

            result = _fetch_headlines_for_ticker("XOM")
            assert result == "headline check unavailable"


# ---------------------------------------------------------------------------
# Tests: handle_two_sigma_interrupts
# ---------------------------------------------------------------------------


class TestHandleTwoSigmaInterrupts:
    def setup_method(self):
        """Clear the dedup tracker before each test."""
        import scripts.price_poller as pp
        pp._two_sigma_fired_today.clear()

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_triggers_when_move_exceeds_two_sigma(
        self, mock_headlines, mock_telegram
    ):
        """A move of 3% when 90d std is 1% should trigger (3% >= 2*1%)."""
        mock_headlines.return_value = "Earnings surprise"

        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        # Create returns with std_dev ~1%, but last return is 3%
        returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.03)
        price_service.compute_daily_returns.return_value = returns

        handle_two_sigma_interrupts(book, price_service)

        # Should have sent a Telegram alert
        mock_telegram.assert_called_once()
        call_msg = mock_telegram.call_args[0][0]
        assert "Two-Sigma Interrupt" in call_msg
        assert "XOM" in call_msg
        assert "Earnings surprise" in call_msg

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_no_trigger_when_move_below_two_sigma(
        self, mock_headlines, mock_telegram
    ):
        """A move of 0.5% when 90d std is ~1% should NOT trigger (0.5% < 2*~1%)."""
        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.005)
        price_service.compute_daily_returns.return_value = returns

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_dedup_prevents_repeat_alert_same_day(
        self, mock_headlines, mock_telegram
    ):
        """A second call on the same day should NOT trigger a second alert."""
        mock_headlines.return_value = "no visible catalyst"

        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.03)
        price_service.compute_daily_returns.return_value = returns

        # First call — triggers
        handle_two_sigma_interrupts(book, price_service)
        assert mock_telegram.call_count == 1

        # Second call — should be deduped
        handle_two_sigma_interrupts(book, price_service)
        assert mock_telegram.call_count == 1

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_triggers_for_negative_moves(
        self, mock_headlines, mock_telegram
    ):
        """A large negative move should also trigger (uses abs value)."""
        mock_headlines.return_value = "no visible catalyst"

        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=-0.04)
        price_service.compute_daily_returns.return_value = returns

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_called_once()
        call_msg = mock_telegram.call_args[0][0]
        assert "-" in call_msg  # negative move shown

    @patch("scripts.price_poller.send_telegram")
    def test_skips_with_insufficient_data(self, mock_telegram):
        """If fewer than 20 data points, should skip without error."""
        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        # Only 10 data points
        returns = pd.Series(np.random.normal(0, 0.01, 10))
        price_service.compute_daily_returns.return_value = returns

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    def test_skips_empty_returns(self, mock_telegram):
        """If no returns data, should skip gracefully."""
        book = make_book([make_position("XOM")])
        price_service = MagicMock()
        price_service.compute_daily_returns.return_value = pd.Series(dtype=float)

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_handles_hedge_ticker_separately(
        self, mock_headlines, mock_telegram
    ):
        """Both primary and hedge tickers should be checked independently."""
        mock_headlines.return_value = "no visible catalyst"

        book = make_book([make_position("XLE", hedge_ticker="RSP")])
        price_service = MagicMock()

        # XLE triggers (big move), RSP doesn't
        xle_returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.04)
        rsp_returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.005)

        def mock_compute(ticker, lookback_days=95):
            if ticker == "XLE":
                return xle_returns
            return rsp_returns

        price_service.compute_daily_returns.side_effect = mock_compute

        handle_two_sigma_interrupts(book, price_service)

        # Only XLE should trigger
        assert mock_telegram.call_count == 1
        call_msg = mock_telegram.call_args[0][0]
        assert "XLE" in call_msg

    @patch("scripts.price_poller.send_telegram")
    def test_handles_exception_gracefully(self, mock_telegram):
        """If price_service raises for one ticker, others still get checked."""
        import scripts.price_poller as pp
        pp._two_sigma_fired_today.clear()

        book = make_book([
            make_position("BAD"),
            make_position("GOOD"),
        ])
        price_service = MagicMock()

        good_returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.03)

        def mock_compute(ticker, lookback_days=95):
            if ticker == "BAD":
                raise RuntimeError("API failure")
            return good_returns

        price_service.compute_daily_returns.side_effect = mock_compute

        # Should not crash, and GOOD should still trigger
        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_called_once()
        call_msg = mock_telegram.call_args[0][0]
        assert "GOOD" in call_msg

    @patch("scripts.price_poller.send_telegram")
    def test_no_positions_returns_immediately(self, mock_telegram):
        """With no active positions, should do nothing."""
        book = make_book([])
        price_service = MagicMock()

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_not_called()
        price_service.compute_daily_returns.assert_not_called()

    @patch("scripts.price_poller.send_telegram")
    @patch("scripts.price_poller._fetch_headlines_for_ticker")
    def test_alert_message_format(self, mock_headlines, mock_telegram):
        """Alert message should include move %, threshold, and cause."""
        mock_headlines.return_value = "Oil prices surge on OPEC cut"

        book = make_book([make_position("XOM")])
        price_service = MagicMock()

        returns = make_daily_returns(n_days=95, std_dev=0.01, last_return=0.025)
        price_service.compute_daily_returns.return_value = returns

        handle_two_sigma_interrupts(book, price_service)

        mock_telegram.assert_called_once()
        msg = mock_telegram.call_args[0][0]
        # Check format: "Two-Sigma Interrupt: {ticker} moved {magnitude}% (2sigma = {threshold}%). Cause: {cause}"
        assert "Two-Sigma Interrupt" in msg
        assert "XOM" in msg
        assert "2σ" in msg
        assert "Cause:" in msg
        assert "Oil prices surge on OPEC cut" in msg
