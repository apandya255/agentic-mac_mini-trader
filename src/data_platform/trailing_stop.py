"""
Trailing Stop Engine for the Agentic AI Trading System.

Per partner update (revised risk law):
- Fixed stops are gone — it's a 2-3% max drawdown TRAILING from peak now
- Trails ratchet and winners lock gains (peak only moves up, never down)
- +5% target is a PM review (take is default, extending has to be argued
  with a re-affirmed flip-condition)
- Sizing 2-5% by conviction, plus a high-conviction tier: up to 8%, max 2 slots

This module computes stop levels and flags — it does NOT decide whether
to exit (that's the PM agent's job). It just answers:
  1. Where is the trailing stop right now?
  2. Has it been breached?
  3. Has the +5% PM review been triggered?

Usage:
    stop = TrailingStop(
        ticker="XOM",
        direction="long",
        entry_price=105.00,
        trail_pct=0.025,  # 2.5% trail
    )
    stop.update(108.00)  # new high → stop ratchets up
    stop.update(106.50)  # pullback, stop stays
    stop.update(104.80)  # breach? check stop.is_stopped
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class TrailingStop:
    """
    Per-position trailing stop tracker.

    The stop trails the peak P&L of the position. For longs, it ratchets
    up as price makes new highs. For shorts, it ratchets down as price
    makes new lows. The stop never moves against the position.

    Attributes:
        ticker: Position ticker.
        direction: "long" or "short".
        entry_price: Price at which the position was entered.
        trail_pct: Trailing stop distance as a decimal (0.02 = 2%, 0.03 = 3%).
        peak_price: Highest price since entry (longs) or lowest (shorts).
        stop_level: Current trailing stop level.
        is_stopped: Whether current price has breached the stop.
        is_target_review: Whether position has reached +5% (PM review trigger).
        current_price: Most recent price fed into the tracker.
    """

    ticker: str
    direction: str  # "long" or "short"
    entry_price: float
    trail_pct: float = 0.025  # default 2.5% — PM sets per conviction tier

    # State (updated via .update())
    peak_price: float = field(init=False)
    stop_level: float = field(init=False)
    current_price: float = field(init=False)
    is_stopped: bool = field(init=False, default=False)
    is_target_review: bool = field(init=False, default=False)
    last_updated: Optional[datetime] = field(init=False, default=None)

    # Configuration
    target_review_pct: float = 0.05  # +5% triggers PM review

    def __post_init__(self):
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got '{self.direction}'")
        if self.trail_pct <= 0 or self.trail_pct >= 1:
            raise ValueError(f"trail_pct must be between 0 and 1, got {self.trail_pct}")

        self.peak_price = self.entry_price
        self.current_price = self.entry_price
        self.stop_level = self._compute_stop(self.entry_price)

    def _compute_stop(self, from_price: float) -> float:
        """Compute stop level given a reference price (the peak)."""
        if self.direction == "long":
            # Stop is below the peak
            return from_price * (1.0 - self.trail_pct)
        else:
            # For shorts, stop is above the trough (peak for shorts = lowest price)
            return from_price * (1.0 + self.trail_pct)

    def update(self, price: float) -> None:
        """
        Feed a new price into the tracker.

        - Ratchets the peak if price makes a new high (long) or low (short)
        - Recomputes the stop level from the new peak
        - Checks if the stop has been breached
        - Checks if +5% target review has been triggered

        Call this once per day (EOD close) or intraday if monitoring tighter.
        """
        self.current_price = price
        self.last_updated = datetime.now()

        # Ratchet the peak (only moves in the favorable direction)
        if self.direction == "long":
            if price > self.peak_price:
                self.peak_price = price
                self.stop_level = self._compute_stop(self.peak_price)
            # Check stop breach: price fell below stop
            self.is_stopped = price <= self.stop_level
        else:
            if price < self.peak_price:
                self.peak_price = price
                self.stop_level = self._compute_stop(self.peak_price)
            # Check stop breach: price rose above stop
            self.is_stopped = price >= self.stop_level

        # Check +5% target review trigger
        self.is_target_review = self.pnl_pct >= self.target_review_pct

    @property
    def pnl_pct(self) -> float:
        """Current P&L as a percentage of entry (positive = profit)."""
        if self.direction == "long":
            return (self.current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.current_price) / self.entry_price

    @property
    def pnl_from_peak_pct(self) -> float:
        """Drawdown from peak P&L (how much has been given back)."""
        if self.direction == "long":
            peak_pnl = (self.peak_price - self.entry_price) / self.entry_price
            current_pnl = (self.current_price - self.entry_price) / self.entry_price
        else:
            peak_pnl = (self.entry_price - self.peak_price) / self.entry_price
            current_pnl = (self.entry_price - self.current_price) / self.entry_price

        return current_pnl - peak_pnl  # negative = given back gains

    @property
    def distance_to_stop_pct(self) -> float:
        """How far current price is from the stop, as a percentage."""
        if self.direction == "long":
            return (self.current_price - self.stop_level) / self.current_price
        else:
            return (self.stop_level - self.current_price) / self.current_price

    @property
    def gains_locked_pct(self) -> float:
        """
        How much gain is 'locked in' by the trailing stop.
        This is the guaranteed minimum P&L if stopped out at current trail.
        Can be negative if stop is below entry (position hasn't moved enough).
        """
        if self.direction == "long":
            return (self.stop_level - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.stop_level) / self.entry_price

    def status(self) -> dict:
        """Return a full status snapshot as a dictionary."""
        return {
            "ticker": self.ticker,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "peak_price": self.peak_price,
            "stop_level": round(self.stop_level, 4),
            "trail_pct": self.trail_pct,
            "pnl_pct": round(self.pnl_pct, 4),
            "pnl_from_peak_pct": round(self.pnl_from_peak_pct, 4),
            "distance_to_stop_pct": round(self.distance_to_stop_pct, 4),
            "gains_locked_pct": round(self.gains_locked_pct, 4),
            "is_stopped": self.is_stopped,
            "is_target_review": self.is_target_review,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


# ---------------------------------------------------------------------------
# Conviction-Based Trail Width
# ---------------------------------------------------------------------------

def trail_pct_for_conviction(conviction: int, high_conviction_slot: bool = False) -> float:
    """
    Determine trail percentage based on conviction tier.

    Per partner spec:
    - Sizing 2-5% by conviction
    - High-conviction tier: up to 8%, max 2 slots

    Trail width scales inversely with conviction:
    - Low conviction (sizing 2%) → tighter trail (2%)
    - High conviction (sizing 5%) → wider trail (3%)
    - High-conviction slot (8%) → widest trail (3%)

    This is a reasonable default; PM can override per-position.
    """
    if high_conviction_slot:
        return 0.03  # 3% trail for high-conviction slots

    if conviction <= 5:
        return 0.02  # 2% for low conviction
    elif conviction <= 7:
        return 0.025  # 2.5% for medium
    else:
        return 0.03  # 3% for high conviction


# ---------------------------------------------------------------------------
# Batch Position Monitoring
# ---------------------------------------------------------------------------

@dataclass
class StopAlert:
    """An alert generated by the stop monitoring system."""
    ticker: str
    alert_type: str  # "stopped_out" | "near_stop" | "target_review"
    detail: str
    urgency: str  # "critical" | "warning" | "info"


def monitor_positions(
    stops: list[TrailingStop],
    near_stop_threshold: float = 0.005,  # flag if within 50bps of stop
) -> list[StopAlert]:
    """
    Scan all active trailing stops and generate alerts.

    Args:
        stops: List of active TrailingStop instances (already updated with current prices).
        near_stop_threshold: Distance from stop (as decimal) that triggers a warning.

    Returns:
        List of StopAlert instances for positions requiring attention.
    """
    alerts: list[StopAlert] = []

    for stop in stops:
        if stop.is_stopped:
            alerts.append(StopAlert(
                ticker=stop.ticker,
                alert_type="stopped_out",
                detail=(
                    f"{stop.ticker} ({stop.direction}) STOPPED OUT at {stop.current_price:.2f}. "
                    f"Entry: {stop.entry_price:.2f}, Peak: {stop.peak_price:.2f}, "
                    f"Stop: {stop.stop_level:.2f}. P&L: {stop.pnl_pct*100:.2f}%"
                ),
                urgency="critical",
            ))

        elif stop.distance_to_stop_pct <= near_stop_threshold:
            alerts.append(StopAlert(
                ticker=stop.ticker,
                alert_type="near_stop",
                detail=(
                    f"{stop.ticker} ({stop.direction}) within {stop.distance_to_stop_pct*100:.1f}% "
                    f"of trailing stop. Price: {stop.current_price:.2f}, Stop: {stop.stop_level:.2f}"
                ),
                urgency="warning",
            ))

        if stop.is_target_review:
            alerts.append(StopAlert(
                ticker=stop.ticker,
                alert_type="target_review",
                detail=(
                    f"{stop.ticker} ({stop.direction}) at +{stop.pnl_pct*100:.1f}% "
                    f"(>+5% threshold). PM review: take profit is default, "
                    f"extending requires re-affirmed flip-condition."
                ),
                urgency="info",
            ))

    return alerts
