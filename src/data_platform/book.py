"""
Book State Manager for the Agentic AI Trading System.

Ties together all other modules into a coherent portfolio view.
Holds positions, marks them to market, computes aggregate metrics,
and outputs the formatted blotter.

Per partner spec:
- Every position is one line at a level (pairs as the ratio, XLE/RSP @ 0.52)
- Legs live in the journal
- NAV = $650mm, cash earns SOFR

Usage:
    from data_platform.book import Book
    book = Book(nav=650_000_000)
    book.add_position("XOM", "long", entry_price=105.0, size_pct=0.02, conviction=8)
    book.mark_to_market(price_service)
    print(book.blotter())
    print(book.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from .trailing_stop import TrailingStop, trail_pct_for_conviction
from .universe import get_hedge


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """A single position in the book (one line = pair expressed as ratio)."""

    # Identity
    ticker: str
    direction: str  # "long" or "short"
    hedge_ticker: str
    hedge_direction: str

    # Entry
    entry_price: float
    hedge_entry_price: float
    entry_date: date
    size_pct_nav: float
    conviction: int
    tier: str = "standard"  # "standard" | "high_conviction"

    # Current state (updated by mark_to_market)
    current_price: float = 0.0
    hedge_current_price: float = 0.0
    pair_ratio: float = 0.0  # ticker / hedge_ticker

    # Trailing stop
    trailing_stop: Optional[TrailingStop] = field(default=None, repr=False)

    # Status
    status: str = "active"  # "active" | "stopped_out" | "target_review" | "closed"
    closed_date: Optional[date] = None
    close_reason: Optional[str] = None

    # P&L
    pnl_pct: float = 0.0
    pnl_dollars: float = 0.0

    def __post_init__(self):
        self.current_price = self.entry_price
        self.hedge_current_price = self.hedge_entry_price
        if self.hedge_entry_price > 0:
            self.pair_ratio = self.entry_price / self.hedge_entry_price

        # Initialize trailing stop
        trail = trail_pct_for_conviction(
            self.conviction,
            high_conviction_slot=(self.tier == "high_conviction"),
        )
        self.trailing_stop = TrailingStop(
            ticker=self.ticker,
            direction=self.direction,
            entry_price=self.entry_price,
            trail_pct=trail,
        )

    @property
    def position_id(self) -> str:
        """Unique identifier for this position."""
        return f"{self.ticker}/{self.hedge_ticker}_{self.entry_date.isoformat()}"

    @property
    def pair_display(self) -> str:
        """Partner's format: 'XLE/RSP @ 0.52'"""
        return f"{self.ticker}/{self.hedge_ticker} @ {self.pair_ratio:.4f}"

    def update_prices(self, ticker_price: float, hedge_price: float) -> None:
        """Update current prices and recompute P&L and ratio."""
        self.current_price = ticker_price
        self.hedge_current_price = hedge_price

        if hedge_price > 0:
            self.pair_ratio = ticker_price / hedge_price

        # Compute pair P&L (long ticker / short hedge or vice versa)
        if self.direction == "long":
            ticker_ret = (ticker_price - self.entry_price) / self.entry_price
            hedge_ret = (hedge_price - self.hedge_entry_price) / self.hedge_entry_price
            # Net P&L = long leg gain - short leg loss (hedge moves against us)
            self.pnl_pct = ticker_ret - hedge_ret
        else:
            ticker_ret = (self.entry_price - ticker_price) / self.entry_price
            hedge_ret = (self.hedge_entry_price - hedge_price) / self.hedge_entry_price
            self.pnl_pct = ticker_ret - hedge_ret

        # Update trailing stop with primary leg price
        if self.trailing_stop:
            self.trailing_stop.update(ticker_price)
            if self.trailing_stop.is_stopped and self.status == "active":
                self.status = "stopped_out"
            elif self.trailing_stop.is_target_review and self.status == "active":
                self.status = "target_review"

    def close(self, reason: str = "manual") -> None:
        """Close the position."""
        self.status = "closed"
        self.closed_date = date.today()
        self.close_reason = reason


# ---------------------------------------------------------------------------
# Book
# ---------------------------------------------------------------------------

DEFAULT_NAV = 650_000_000


class Book:
    """
    Portfolio state manager.

    Holds all active and closed positions, computes aggregate metrics,
    and produces the formatted blotter output.
    """

    def __init__(self, nav: float = DEFAULT_NAV):
        self.initial_nav = nav
        self.cash_nav = nav  # starts fully in cash
        self.positions: list[Position] = []
        self._trade_journal: list[dict] = []

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    def add_position(
        self,
        ticker: str,
        direction: str,
        entry_price: float,
        size_pct: float,
        conviction: int,
        hedge_entry_price: Optional[float] = None,
        tier: str = "standard",
    ) -> Position:
        """
        Add a new position to the book.

        Automatically resolves the hedge via universe.get_hedge().
        If hedge_entry_price is not provided, assumes it must be set later
        via mark_to_market.

        Args:
            ticker: Primary leg ticker.
            direction: "long" or "short".
            entry_price: Entry price of primary leg.
            size_pct: Size as fraction of NAV (e.g., 0.04 = 4%).
            conviction: Conviction score (1-10).
            hedge_entry_price: Entry price of hedge leg. If None, defaults to 0.
            tier: "standard" or "high_conviction".

        Returns:
            The created Position.
        """
        # Resolve hedge
        hedge_pair = get_hedge(ticker, direction)
        if hedge_pair is None:
            raise ValueError(f"Cannot resolve hedge for {ticker}. Not in universe.")

        pos = Position(
            ticker=ticker,
            direction=direction,
            hedge_ticker=hedge_pair.hedge_ticker,
            hedge_direction=hedge_pair.hedge_direction,
            entry_price=entry_price,
            hedge_entry_price=hedge_entry_price or 0.0,
            entry_date=date.today(),
            size_pct_nav=size_pct,
            conviction=conviction,
            tier=tier,
        )

        self.positions.append(pos)

        # Reduce cash by position notional (both legs)
        notional = self.initial_nav * size_pct * 2  # both legs
        self.cash_nav -= notional

        # Journal entry
        self._trade_journal.append({
            "action": "open",
            "position_id": pos.position_id,
            "ticker": ticker,
            "direction": direction,
            "hedge": hedge_pair.hedge_ticker,
            "size_pct": size_pct,
            "entry_price": entry_price,
            "conviction": conviction,
            "tier": tier,
            "date": date.today().isoformat(),
        })

        return pos

    def close_position(self, ticker: str, reason: str = "manual") -> Optional[Position]:
        """Close an active position by ticker."""
        for pos in self.active_positions:
            if pos.ticker == ticker:
                pos.close(reason)
                # Return cash
                notional = self.initial_nav * pos.size_pct_nav * 2
                self.cash_nav += notional
                self._trade_journal.append({
                    "action": "close",
                    "position_id": pos.position_id,
                    "ticker": ticker,
                    "reason": reason,
                    "pnl_pct": round(pos.pnl_pct, 4),
                    "date": date.today().isoformat(),
                })
                return pos
        return None

    # ------------------------------------------------------------------
    # Mark to Market
    # ------------------------------------------------------------------

    def mark_to_market(self, price_service) -> None:
        """
        Update all active positions with current prices from PriceService.

        Args:
            price_service: A PriceService instance with current data.
        """
        for pos in self.active_positions:
            ticker_price = price_service.get_latest_close(pos.ticker)
            hedge_price = price_service.get_latest_close(pos.hedge_ticker)

            if ticker_price and hedge_price:
                pos.update_prices(ticker_price, hedge_price)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def active_positions(self) -> list[Position]:
        """All currently active positions."""
        return [p for p in self.positions if p.status in ("active", "target_review")]

    @property
    def closed_positions(self) -> list[Position]:
        """All closed positions."""
        return [p for p in self.positions if p.status in ("closed", "stopped_out")]

    @property
    def position_count(self) -> int:
        return len(self.active_positions)

    @property
    def gross_exposure_pct(self) -> float:
        """Total gross exposure as % of NAV (sum of all position sizes × 2 for both legs)."""
        return sum(p.size_pct_nav for p in self.active_positions) * 2

    @property
    def net_exposure_pct(self) -> float:
        """Net directional exposure (longs - shorts as % of NAV)."""
        net = 0.0
        for p in self.active_positions:
            if p.direction == "long":
                net += p.size_pct_nav
            else:
                net -= p.size_pct_nav
        return net

    @property
    def cash_pct(self) -> float:
        """Cash as fraction of initial NAV."""
        return max(0.0, self.cash_nav / self.initial_nav)

    @property
    def current_nav(self) -> float:
        """Current NAV = cash + sum of position P&Ls."""
        pnl = sum(
            p.pnl_pct * p.size_pct_nav * self.initial_nav
            for p in self.active_positions
        )
        return self.initial_nav + pnl

    @property
    def total_pnl_pct(self) -> float:
        """Total book P&L as % of initial NAV."""
        return (self.current_nav - self.initial_nav) / self.initial_nav

    # ------------------------------------------------------------------
    # Daily Returns (for factor beta computation)
    # ------------------------------------------------------------------

    def compute_daily_returns(self, price_service, lookback_days: int = 252) -> pd.Series:
        """
        Compute the book's daily return series from active positions.

        This is a simplified computation: weights each position's daily return
        by its size_pct_nav.

        For a proper implementation, this would use the full historical position
        set (including closed positions during the window). This version uses
        current active positions as a proxy.
        """
        if not self.active_positions:
            return pd.Series(dtype=float, name="book")

        weighted_returns = None

        for pos in self.active_positions:
            # Get daily returns for primary leg
            rets = price_service.compute_daily_returns(pos.ticker, lookback_days)
            hedge_rets = price_service.compute_daily_returns(pos.hedge_ticker, lookback_days)

            if rets.empty or hedge_rets.empty:
                continue

            # Pair return = primary - hedge (for long); hedge - primary (for short)
            combined = pd.DataFrame({"p": rets, "h": hedge_rets}).dropna()
            if pos.direction == "long":
                pair_ret = combined["p"] - combined["h"]
            else:
                pair_ret = combined["h"] - combined["p"]

            # Weight by position size
            weighted = pair_ret * pos.size_pct_nav

            if weighted_returns is None:
                weighted_returns = weighted
            else:
                weighted_returns = weighted_returns.add(weighted, fill_value=0.0)

        if weighted_returns is None:
            return pd.Series(dtype=float, name="book")

        return weighted_returns.rename("book")

    # ------------------------------------------------------------------
    # Output: Blotter
    # ------------------------------------------------------------------

    def blotter(self) -> list[str]:
        """
        Return the book as a list of one-line position strings.
        Format per partner spec: 'XLE/RSP @ 0.5234  +2.1%  [8/10] trailing@107.25'
        """
        lines = []
        for pos in self.active_positions:
            stop_info = ""
            if pos.trailing_stop:
                stop_info = f"trail@{pos.trailing_stop.stop_level:.2f}"

            status_flag = ""
            if pos.status == "target_review":
                status_flag = " [PM REVIEW]"
            elif pos.status == "stopped_out":
                status_flag = " [STOPPED]"

            line = (
                f"{pos.pair_display}  "
                f"{pos.pnl_pct*100:+.1f}%  "
                f"[{pos.conviction}/10 {pos.tier[0].upper()}]  "
                f"{pos.direction} {pos.size_pct_nav*100:.1f}%  "
                f"{stop_info}{status_flag}"
            )
            lines.append(line)

        return lines

    def summary(self) -> dict:
        """Return a summary snapshot of the book state."""
        return {
            "date": date.today().isoformat(),
            "nav": round(self.current_nav, 2),
            "initial_nav": self.initial_nav,
            "total_pnl_pct": round(self.total_pnl_pct, 5),
            "total_pnl_dollars": round(self.current_nav - self.initial_nav, 2),
            "position_count": self.position_count,
            "gross_exposure_pct": round(self.gross_exposure_pct, 4),
            "net_exposure_pct": round(self.net_exposure_pct, 4),
            "cash_pct": round(self.cash_pct, 4),
            "positions_at_target": sum(1 for p in self.active_positions if p.status == "target_review"),
            "positions_stopped": sum(1 for p in self.positions if p.status == "stopped_out"),
        }

    @property
    def trade_journal(self) -> list[dict]:
        """Full trade journal (all opens and closes)."""
        return self._trade_journal
