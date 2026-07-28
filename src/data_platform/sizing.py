"""
Position Sizing Calculator for the Agentic AI Trading System.

Per partner update:
- Sizing 2-5% by conviction
- High-conviction tier: up to 8%, max 2 slots
- Self-revoking: if HC positions don't out-hit the standard book, they lose the tier
- Circuit breaker multiplier applies (0.8 in warning, 0.0 in breaker)

This module computes position size given conviction and book state.
It does NOT decide conviction — that's the agent/PM's job.

Usage:
    from data_platform.sizing import PositionSizer
    sizer = PositionSizer(nav=650_000_000)
    result = sizer.compute_size(conviction=8, high_conviction=False)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# NAV per partner spec
DEFAULT_NAV = 650_000_000


@dataclass(frozen=True)
class SizingResult:
    """Output of the position sizing calculation."""
    size_pct_nav: float       # final size as % of NAV
    size_dollars: float       # final size in dollars
    conviction: int           # input conviction (1-10)
    tier: str                 # "standard" | "high_conviction"
    base_size_pct: float      # before adjustments
    circuit_breaker_mult: float  # 1.0 / 0.8 / 0.0
    rationale: str


@dataclass
class HighConvictionSlot:
    """Tracks a high-conviction position slot."""
    ticker: str
    entry_date: date
    entry_nav: float
    cumulative_return_pct: float = 0.0
    active: bool = True


class PositionSizer:
    """
    Computes position sizes based on conviction tier and book state.

    Sizing rules (per partner spec):
    - Conviction 1-4:  2% NAV (minimum viable)
    - Conviction 5-6:  3% NAV
    - Conviction 7-8:  4% NAV
    - Conviction 9-10: 5% NAV
    - High-conviction tier: up to 8% NAV (max 2 slots at any time)

    Adjustments:
    - Circuit breaker multiplier (from BookMonitor)
    - HC slots self-revoke if they underperform

    Args:
        nav: Book NAV in dollars.
        max_hc_slots: Maximum high-conviction slots allowed.
    """

    # Conviction -> base size mapping
    CONVICTION_SIZE_MAP: dict[int, float] = {
        1: 0.02, 2: 0.02, 3: 0.02, 4: 0.02,
        5: 0.03, 6: 0.03,
        7: 0.04, 8: 0.04,
        9: 0.05, 10: 0.05,
    }

    HC_MAX_SIZE: float = 0.08  # 8% for high-conviction
    MAX_HC_SLOTS: int = 2

    def __init__(self, nav: float = DEFAULT_NAV, max_hc_slots: int = 2):
        self.nav = nav
        self.max_hc_slots = max_hc_slots
        self._hc_slots: list[HighConvictionSlot] = []

    @property
    def active_hc_slots(self) -> list[HighConvictionSlot]:
        """Currently active high-conviction slots."""
        return [s for s in self._hc_slots if s.active]

    @property
    def hc_slots_available(self) -> int:
        """Number of high-conviction slots remaining."""
        return self.max_hc_slots - len(self.active_hc_slots)

    def compute_size(
        self,
        conviction: int,
        high_conviction: bool = False,
        circuit_breaker_mult: float = 1.0,
        ticker: str = "",
    ) -> SizingResult:
        """
        Compute position size for a new trade.

        Args:
            conviction: Conviction score (1-10).
            high_conviction: Whether this is a high-conviction tier trade (8% max).
            circuit_breaker_mult: Multiplier from BookMonitor (1.0/0.8/0.0).
            ticker: Ticker symbol (for tracking HC slots).

        Returns:
            SizingResult with final size and rationale.
        """
        conviction = max(1, min(10, conviction))

        # Determine base size
        if high_conviction and conviction >= 8:
            if self.hc_slots_available > 0:
                base_pct = self.HC_MAX_SIZE
                tier = "high_conviction"
                rationale = (
                    f"High-conviction tier: {base_pct*100:.0f}% "
                    f"({self.hc_slots_available}/{self.max_hc_slots} HC slots available)"
                )
            else:
                # No HC slots available, fall back to standard
                base_pct = self.CONVICTION_SIZE_MAP[conviction]
                tier = "standard"
                high_conviction = False
                rationale = (
                    f"HC slots exhausted ({self.max_hc_slots}/{self.max_hc_slots} in use). "
                    f"Falling back to standard sizing at {base_pct*100:.0f}%"
                )
        else:
            base_pct = self.CONVICTION_SIZE_MAP[conviction]
            tier = "standard"
            rationale = f"Standard sizing: conviction {conviction}/10 → {base_pct*100:.0f}% NAV"

        # Apply circuit breaker
        final_pct = base_pct * circuit_breaker_mult

        if circuit_breaker_mult < 1.0:
            if circuit_breaker_mult == 0.0:
                rationale += " | BLOCKED by circuit breaker (sizing = 0)"
            else:
                rationale += f" | Reduced by circuit breaker ({circuit_breaker_mult:.1f}x)"

        final_dollars = self.nav * final_pct

        # Register HC slot if applicable
        if high_conviction and tier == "high_conviction" and final_pct > 0:
            self._hc_slots.append(HighConvictionSlot(
                ticker=ticker,
                entry_date=date.today(),
                entry_nav=self.nav,
            ))

        return SizingResult(
            size_pct_nav=round(final_pct, 4),
            size_dollars=round(final_dollars, 2),
            conviction=conviction,
            tier=tier,
            base_size_pct=base_pct,
            circuit_breaker_mult=circuit_breaker_mult,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # High-Conviction Slot Management
    # ------------------------------------------------------------------

    def update_hc_performance(self, ticker: str, cumulative_return_pct: float) -> None:
        """
        Update the performance of a high-conviction slot.
        Used for the self-revoking check.
        """
        for slot in self._hc_slots:
            if slot.ticker == ticker and slot.active:
                slot.cumulative_return_pct = cumulative_return_pct
                break

    def check_hc_revocation(self, standard_book_return_pct: float) -> list[str]:
        """
        Check if any HC slots should self-revoke.

        Per spec: HC positions that don't out-hit the standard book
        lose their high-conviction tier.

        Args:
            standard_book_return_pct: Return of the non-HC portion of the book
                                      over the same period.

        Returns:
            List of tickers that were revoked.
        """
        revoked = []
        for slot in self._hc_slots:
            if not slot.active:
                continue
            # If HC position is underperforming the standard book, revoke
            if slot.cumulative_return_pct < standard_book_return_pct:
                slot.active = False
                revoked.append(slot.ticker)

        return revoked

    def revoke_hc_slot(self, ticker: str) -> bool:
        """Manually revoke a high-conviction slot."""
        for slot in self._hc_slots:
            if slot.ticker == ticker and slot.active:
                slot.active = False
                return True
        return False

    # ------------------------------------------------------------------
    # Sizing Table (for display)
    # ------------------------------------------------------------------

    def sizing_table(self, circuit_breaker_mult: float = 1.0) -> list[dict]:
        """
        Return the full sizing table for all conviction levels.
        Useful for displaying current sizing regime.
        """
        rows = []
        for conv in range(1, 11):
            base = self.CONVICTION_SIZE_MAP[conv]
            final = base * circuit_breaker_mult
            rows.append({
                "conviction": conv,
                "base_pct": base,
                "adjusted_pct": round(final, 4),
                "dollars": round(self.nav * final, 0),
            })

        # Add HC tier
        hc_final = self.HC_MAX_SIZE * circuit_breaker_mult
        rows.append({
            "conviction": "HC (8+)",
            "base_pct": self.HC_MAX_SIZE,
            "adjusted_pct": round(hc_final, 4),
            "dollars": round(self.nav * hc_final, 0),
            "slots_available": self.hc_slots_available,
        })

        return rows
