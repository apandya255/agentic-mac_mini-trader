"""
Book-Level Circuit Breaker for the Agentic AI Trading System.

Per partner update:
- 6%/4% book circuit breaker
- 4% drawdown from peak = warning (review + reduce sizing)
- 6% drawdown from peak = hard stop (emergency deleverage)

This module tracks peak NAV, computes drawdown, and returns status.
It does NOT execute deleveraging — it flags conditions for the Risk
agent and PM agent to act on.

NAV = $650mm per partner spec.

Usage:
    monitor = BookMonitor(initial_nav=650_000_000)
    monitor.update_nav(648_000_000)  # small loss
    print(monitor.status)            # "normal"
    monitor.update_nav(624_000_000)  # 4% drawdown
    print(monitor.status)            # "warning"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# Default NAV per partner spec
DEFAULT_NAV = 650_000_000


@dataclass
class BookMonitor:
    """
    Tracks book-level NAV and computes drawdown from peak.

    Implements the 4%/6% circuit breaker:
    - 0-4% drawdown: "normal"
    - 4-6% drawdown: "warning" (review positions, reduce sizing 20%)
    - 6%+ drawdown: "breaker" (emergency deleverage, halt new positions)

    Attributes:
        initial_nav: Starting NAV.
        current_nav: Most recent NAV.
        peak_nav: High-water mark.
        drawdown_pct: Current drawdown from peak as a decimal.
        status: "normal" | "warning" | "breaker"
    """

    initial_nav: float = DEFAULT_NAV
    warning_threshold: float = 0.04  # 4%
    breaker_threshold: float = 0.06  # 6%

    # State
    current_nav: float = field(init=False)
    peak_nav: float = field(init=False)
    last_updated: Optional[datetime] = field(init=False, default=None)
    _history: list[tuple[str, float]] = field(init=False, default_factory=list)

    # Recovery tracking
    consecutive_positive_days: int = field(init=False, default=0)
    recovery_required_days: int = 5  # per spec: re-lever after 5 positive days
    _prev_nav: float = field(init=False, default=0.0)

    def __post_init__(self):
        self.current_nav = self.initial_nav
        self.peak_nav = self.initial_nav
        self._prev_nav = self.initial_nav

    def update_nav(self, nav: float, as_of: Optional[date] = None) -> None:
        """
        Feed a new NAV reading (typically EOD).

        - Updates the high-water mark if new high
        - Recomputes drawdown
        - Tracks consecutive positive days for recovery

        Args:
            nav: Current book NAV in dollars.
            as_of: Date of this reading (default: today).
        """
        date_str = (as_of or date.today()).isoformat()

        # Track positive days for recovery
        if nav > self._prev_nav:
            self.consecutive_positive_days += 1
        else:
            self.consecutive_positive_days = 0

        self._prev_nav = self.current_nav
        self.current_nav = nav
        self.last_updated = datetime.now()

        # Ratchet peak (only up)
        if nav > self.peak_nav:
            self.peak_nav = nav

        # Store history
        self._history.append((date_str, nav))

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from peak as a decimal (e.g., 0.04 = 4%)."""
        if self.peak_nav == 0:
            return 0.0
        return (self.peak_nav - self.current_nav) / self.peak_nav

    @property
    def drawdown_dollars(self) -> float:
        """Current drawdown from peak in dollars."""
        return self.peak_nav - self.current_nav

    @property
    def status(self) -> str:
        """
        Circuit breaker status:
        - "normal": drawdown < 4%
        - "warning": 4% <= drawdown < 6%
        - "breaker": drawdown >= 6%
        """
        dd = self.drawdown_pct
        if dd >= self.breaker_threshold:
            return "breaker"
        elif dd >= self.warning_threshold:
            return "warning"
        return "normal"

    @property
    def recovery_eligible(self) -> bool:
        """
        Whether the book has met recovery criteria to re-lever.
        Per spec: only re-lever after 5 consecutive positive days.
        """
        return self.consecutive_positive_days >= self.recovery_required_days

    @property
    def pnl_from_inception(self) -> float:
        """Total P&L since inception as a decimal."""
        if self.initial_nav == 0:
            return 0.0
        return (self.current_nav - self.initial_nav) / self.initial_nav

    @property
    def pnl_from_inception_dollars(self) -> float:
        """Total P&L since inception in dollars."""
        return self.current_nav - self.initial_nav

    def sizing_multiplier(self) -> float:
        """
        Sizing reduction multiplier based on circuit breaker status.

        - "normal": 1.0 (full sizing)
        - "warning": 0.8 (reduce sizing 20% per spec)
        - "breaker": 0.0 (halt new positions)
        """
        s = self.status
        if s == "breaker":
            return 0.0
        elif s == "warning":
            return 0.8
        return 1.0

    def max_leverage(self) -> float:
        """
        Maximum allowed gross leverage based on circuit breaker status.

        - "normal": no constraint from circuit breaker (leverage managed by Risk agent)
        - "warning": cap at 1.0x gross (deleverage toward)
        - "breaker": cap at 0.3x gross (emergency)
        """
        s = self.status
        if s == "breaker":
            return 0.3
        elif s == "warning":
            return 1.0
        return 3.0  # absolute ceiling from spec, but Risk agent manages below this

    def snapshot(self) -> dict:
        """Return a full status snapshot as a dictionary."""
        return {
            "current_nav": self.current_nav,
            "peak_nav": self.peak_nav,
            "initial_nav": self.initial_nav,
            "drawdown_pct": round(self.drawdown_pct, 5),
            "drawdown_dollars": round(self.drawdown_dollars, 2),
            "status": self.status,
            "sizing_multiplier": self.sizing_multiplier(),
            "max_leverage": self.max_leverage(),
            "pnl_inception_pct": round(self.pnl_from_inception, 5),
            "pnl_inception_dollars": round(self.pnl_from_inception_dollars, 2),
            "consecutive_positive_days": self.consecutive_positive_days,
            "recovery_eligible": self.recovery_eligible,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    def alert_message(self) -> Optional[str]:
        """
        Generate an alert message if the circuit breaker is triggered.
        Returns None if status is normal.
        """
        s = self.status
        dd = self.drawdown_pct

        if s == "breaker":
            return (
                f"CIRCUIT BREAKER TRIGGERED: Book drawdown {dd*100:.2f}% "
                f"(threshold {self.breaker_threshold*100:.0f}%). "
                f"Emergency deleverage to {self.max_leverage():.1f}x gross. "
                f"Halt all new positions. "
                f"NAV: ${self.current_nav:,.0f} | Peak: ${self.peak_nav:,.0f} | "
                f"Loss: ${self.drawdown_dollars:,.0f}"
            )
        elif s == "warning":
            return (
                f"DRAWDOWN WARNING: Book drawdown {dd*100:.2f}% "
                f"(threshold {self.warning_threshold*100:.0f}%). "
                f"Reduce sizing by 20%. Review lowest-conviction positions. "
                f"NAV: ${self.current_nav:,.0f} | Peak: ${self.peak_nav:,.0f} | "
                f"Loss: ${self.drawdown_dollars:,.0f}"
            )

        return None
