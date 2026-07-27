"""
SOFR / Cash Carry Calculator for the Agentic AI Trading System.

Per partner spec:
- NAV set at $650mm
- Cash earns SOFR
- Positions have an opportunity cost vs. risk-free

Fetches SOFR from FRED (free API, series ID: SOFR) and computes
daily carry for cash allocations and position-level carry costs.

Usage:
    calc = CarryCalculator(fred_api_key="your_key")
    calc.refresh_sofr()
    daily = calc.daily_cash_carry(cash_pct=0.40)  # 40% cash
    cost = calc.position_carry_cost("short", notional=13_000_000)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "carry.db"

# NAV per partner spec
DEFAULT_NAV = 650_000_000  # $650mm


@dataclass(frozen=True)
class CarrySnapshot:
    """Daily carry computation result."""
    as_of_date: date
    sofr_rate_annual: float  # e.g., 0.053 = 5.3%
    nav: float
    cash_pct: float
    cash_notional: float
    daily_carry_usd: float  # cash_notional * sofr / 360
    annualized_carry_usd: float


@dataclass(frozen=True)
class PositionCarryCost:
    """Carry cost for an individual position."""
    ticker: str
    direction: str  # "long" or "short"
    notional: float
    daily_cost_usd: float
    annual_cost_bps: float  # cost expressed in bps of notional
    description: str


class CarryCalculator:
    """
    Computes carry (interest earned on cash) and carry costs (opportunity
    cost of deployed capital and borrow costs for shorts).

    SOFR is fetched from FRED and cached locally in SQLite.
    If no FRED API key is provided, uses a fallback rate.
    """

    def __init__(
        self,
        fred_api_key: Optional[str] = None,
        nav: float = DEFAULT_NAV,
        db_path: Optional[Path] = None,
    ):
        self.fred_api_key = fred_api_key
        self.nav = nav
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the sofr_rates table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sofr_rates (
                    date TEXT PRIMARY KEY,
                    rate REAL NOT NULL
                )
            """)

    # ------------------------------------------------------------------
    # SOFR Data
    # ------------------------------------------------------------------

    def refresh_sofr(self, lookback_days: int = 30) -> int:
        """
        Fetch recent SOFR rates from FRED and store locally.

        Requires fredapi package and a FRED API key.
        Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html

        Returns number of new rates stored.
        """
        if not self.fred_api_key:
            return 0

        try:
            from fredapi import Fred
            fred = Fred(api_key=self.fred_api_key)
            start = date.today() - timedelta(days=lookback_days)
            series = fred.get_series("SOFR", observation_start=start.isoformat())

            if series is None or series.empty:
                return 0

            rows = []
            for dt, val in series.items():
                if val is not None and not (isinstance(val, float) and val != val):
                    # FRED reports SOFR as percentage (e.g., 5.3 for 5.3%)
                    rows.append((dt.strftime("%Y-%m-%d"), float(val) / 100.0))

            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO sofr_rates (date, rate) VALUES (?, ?)",
                    rows,
                )

            return len(rows)

        except Exception:
            return 0

    def get_current_sofr(self) -> float:
        """
        Get the most recent SOFR rate from local DB.
        Returns the rate as a decimal (e.g., 0.053 for 5.3%).
        Falls back to 0.05 (5%) if no data available.
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT rate FROM sofr_rates ORDER BY date DESC LIMIT 1"
            ).fetchone()

        if row:
            return row[0]

        # Fallback: reasonable estimate if no FRED data yet
        return 0.05

    def get_sofr_history(self, days: int = 30) -> list[tuple[str, float]]:
        """Return recent SOFR rates as (date_str, rate) tuples."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT date, rate FROM sofr_rates ORDER BY date DESC LIMIT ?",
                (days,),
            ).fetchall()
        return rows

    # ------------------------------------------------------------------
    # Cash Carry
    # ------------------------------------------------------------------

    def daily_cash_carry(
        self,
        cash_pct: float,
        as_of: Optional[date] = None,
    ) -> CarrySnapshot:
        """
        Compute daily carry earned on cash allocation.

        Args:
            cash_pct: Fraction of NAV in cash (e.g., 0.40 for 40%).
            as_of: Date for the computation (default: today).

        Returns:
            CarrySnapshot with daily and annualized carry in USD.

        Note: Uses actual/360 day count convention (money market standard).
        """
        sofr = self.get_current_sofr()
        cash_notional = self.nav * cash_pct
        daily_carry = cash_notional * sofr / 360.0
        annualized_carry = cash_notional * sofr

        return CarrySnapshot(
            as_of_date=as_of or date.today(),
            sofr_rate_annual=sofr,
            nav=self.nav,
            cash_pct=cash_pct,
            cash_notional=cash_notional,
            daily_carry_usd=round(daily_carry, 2),
            annualized_carry_usd=round(annualized_carry, 2),
        )

    # ------------------------------------------------------------------
    # Position-Level Carry Cost
    # ------------------------------------------------------------------

    def position_carry_cost(
        self,
        direction: str,
        notional: float,
        ticker: str = "",
        borrow_rate_override: Optional[float] = None,
    ) -> PositionCarryCost:
        """
        Compute carry cost for a single position.

        For longs: opportunity cost = notional could have earned SOFR in cash.
        For shorts: borrow cost = estimated borrow rate on the short notional.

        Args:
            direction: "long" or "short"
            notional: Dollar notional of the position.
            ticker: Ticker symbol (for labeling).
            borrow_rate_override: Override borrow rate for shorts.
                                   Default estimates: 0.5% for liquid names,
                                   higher for hard-to-borrow.

        Returns:
            PositionCarryCost with daily cost and annualized bps.
        """
        sofr = self.get_current_sofr()

        if direction == "long":
            # Opportunity cost: this capital could be earning SOFR
            annual_cost = notional * sofr
            daily_cost = annual_cost / 360.0
            annual_bps = sofr * 10000  # convert to bps
            desc = f"Opportunity cost vs. SOFR ({sofr*100:.2f}%)"

        elif direction == "short":
            # Borrow cost: estimated cost to maintain the short
            borrow_rate = borrow_rate_override if borrow_rate_override is not None else 0.005
            # Short also earns rebate (SOFR - spread), net cost = borrow - rebate
            # Simplified: net cost = borrow_rate (already the net figure)
            annual_cost = notional * borrow_rate
            daily_cost = annual_cost / 360.0
            annual_bps = borrow_rate * 10000
            desc = f"Borrow cost ({borrow_rate*100:.2f}% annualized)"

        else:
            raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")

        return PositionCarryCost(
            ticker=ticker,
            direction=direction,
            notional=notional,
            daily_cost_usd=round(daily_cost, 2),
            annual_cost_bps=round(annual_bps, 1),
            description=desc,
        )

    # ------------------------------------------------------------------
    # Book-Level Carry Summary
    # ------------------------------------------------------------------

    def book_carry_summary(
        self,
        positions: list[dict],
        cash_pct: float,
    ) -> dict:
        """
        Compute total daily carry for the book (cash earn minus position costs).

        Args:
            positions: List of dicts with keys: ticker, direction, notional
            cash_pct: Fraction of NAV in cash.

        Returns:
            Dict with cash_carry, total_position_cost, net_daily_carry (all in USD).
        """
        cash_snap = self.daily_cash_carry(cash_pct)

        total_position_cost = 0.0
        for pos in positions:
            cost = self.position_carry_cost(
                direction=pos["direction"],
                notional=pos["notional"],
                ticker=pos.get("ticker", ""),
            )
            total_position_cost += cost.daily_cost_usd

        net_daily = cash_snap.daily_carry_usd - total_position_cost

        return {
            "date": date.today().isoformat(),
            "sofr_rate": cash_snap.sofr_rate_annual,
            "nav": self.nav,
            "cash_pct": cash_pct,
            "cash_daily_carry_usd": cash_snap.daily_carry_usd,
            "position_daily_cost_usd": round(total_position_cost, 2),
            "net_daily_carry_usd": round(net_daily, 2),
            "net_annual_carry_usd": round(net_daily * 360, 2),
        }
