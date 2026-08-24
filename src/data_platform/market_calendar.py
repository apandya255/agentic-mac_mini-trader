"""
Market calendar module for the Agentic AI Trading System.

Provides functions to determine whether US equity markets are open,
whether a given date is a trading day, whether the FX session is active,
and to compute the next market open time for sleep-until logic.

Uses a static holiday list (updated annually) and pytz for Eastern Time handling.

Usage:
    from src.data_platform.market_calendar import (
        is_market_open,
        is_trading_day,
        is_fx_session_active,
        is_equity_stale_check_suppressed,
        is_fx_stale_check_suppressed,
        next_market_open,
    )

    if is_market_open():
        poll_prices()
    elif is_equity_stale_check_suppressed():
        # Don't flag equity tickers as stale when market is closed
        pass

    if is_fx_stale_check_suppressed():
        # Don't flag FX tickers as stale during session gaps
        pass
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytz

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ET = pytz.timezone("America/New_York")

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# FX session boundaries (in ET)
FX_SESSION_START_DAY = 6  # Sunday (weekday() == 6)
FX_SESSION_START_TIME = time(17, 0)
FX_SESSION_END_DAY = 4  # Friday (weekday() == 4)
FX_SESSION_END_TIME = time(17, 0)

# ---------------------------------------------------------------------------
# US Market Holidays — updated annually
# ---------------------------------------------------------------------------

US_MARKET_HOLIDAYS: dict[int, list[str]] = {
    2025: [
        "2025-01-01",  # New Year's Day
        "2025-01-20",  # MLK Day
        "2025-02-17",  # Presidents' Day
        "2025-04-18",  # Good Friday
        "2025-05-26",  # Memorial Day
        "2025-06-19",  # Juneteenth
        "2025-07-04",  # Independence Day
        "2025-09-01",  # Labor Day
        "2025-11-27",  # Thanksgiving
        "2025-12-25",  # Christmas
    ],
    2026: [
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # MLK Day
        "2026-02-16",  # Presidents' Day
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-06-19",  # Juneteenth
        "2026-07-03",  # Independence Day (observed)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Christmas
    ],
}

# Pre-compute a flat set of date objects for fast lookup
_HOLIDAY_DATES: set[date] = set()
for _year_holidays in US_MARKET_HOLIDAYS.values():
    for _ds in _year_holidays:
        _HOLIDAY_DATES.add(date.fromisoformat(_ds))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_market_open(now: datetime | None = None) -> bool:
    """
    True if the current (or provided) time falls within US equity market
    regular trading hours: Monday–Friday, 09:30–16:00 ET, excluding
    US market holidays.

    Parameters
    ----------
    now : datetime, optional
        A timezone-aware or naive datetime. If naive, assumed to be UTC.
        If None, uses the current time.

    Returns
    -------
    bool
    """
    now_et = _to_et(now)
    d = now_et.date()
    t = now_et.time()

    # Must be a weekday
    if d.weekday() >= 5:
        return False

    # Must not be a holiday
    if d in _HOLIDAY_DATES:
        return False

    # Must be within market hours (inclusive of open, exclusive of close)
    return MARKET_OPEN <= t < MARKET_CLOSE


def is_trading_day(dt: date | None = None) -> bool:
    """
    True if the given date is a weekday and not a US market holiday.

    Parameters
    ----------
    dt : date, optional
        The date to check. If None, uses today in ET.

    Returns
    -------
    bool
    """
    if dt is None:
        dt = datetime.now(ET).date()

    # Must be a weekday
    if dt.weekday() >= 5:
        return False

    # Must not be a holiday
    return dt not in _HOLIDAY_DATES


def is_fx_session_active(now: datetime | None = None) -> bool:
    """
    True if the FX session is active: Sunday 17:00 ET through Friday 17:00 ET.

    The global FX market operates continuously from Sunday evening (when
    Sydney/Wellington open) through Friday afternoon (when New York closes).

    Parameters
    ----------
    now : datetime, optional
        A timezone-aware or naive datetime. If None, uses the current time.

    Returns
    -------
    bool
    """
    now_et = _to_et(now)
    weekday = now_et.weekday()  # Mon=0, Sun=6
    t = now_et.time()

    # Saturday: always closed
    if weekday == 5:
        return False

    # Sunday: open only at or after 17:00
    if weekday == 6:
        return t >= FX_SESSION_START_TIME

    # Friday: open only before 17:00
    if weekday == 4:
        return t < FX_SESSION_END_TIME

    # Monday through Thursday: always open
    return True


def is_equity_stale_check_suppressed(now: datetime | None = None) -> bool:
    """
    True if equity staleness checks should be suppressed because the
    US equity market is currently closed.

    Staleness checks are suppressed when:
    - It is a weekend (Saturday or Sunday)
    - It is a US market holiday
    - It is outside regular trading hours (before 09:30 or after 16:00 ET)

    Parameters
    ----------
    now : datetime, optional
        A timezone-aware or naive datetime. If None, uses the current time.

    Returns
    -------
    bool
        True if staleness checks should be suppressed (market closed).
    """
    return not is_market_open(now)


def is_fx_stale_check_suppressed(now: datetime | None = None) -> bool:
    """
    True if FX staleness checks should be suppressed because the FX
    session is inactive.

    The FX session is inactive (and staleness checks suppressed) during:
    - All of Saturday (weekday == 5)
    - Sunday before 17:00 ET (session hasn't opened yet)

    Parameters
    ----------
    now : datetime, optional
        A timezone-aware or naive datetime. If None, uses the current time.

    Returns
    -------
    bool
        True if FX staleness checks should be suppressed (session inactive).
    """
    return not is_fx_session_active(now)


def next_market_open(now: datetime | None = None) -> datetime:
    """
    Return the next datetime when the US equity market opens (09:30 ET),
    for sleep-until calculations.

    If the market is currently open, returns the *next* open (i.e., tomorrow
    or the next trading day). If the market is closed, returns the next
    upcoming 09:30 ET on a trading day.

    Parameters
    ----------
    now : datetime, optional
        A timezone-aware or naive datetime. If None, uses the current time.

    Returns
    -------
    datetime
        Timezone-aware datetime in ET representing the next market open.
    """
    now_et = _to_et(now)

    # Start searching from the next candidate day
    # If we're before market open today, today could be the answer
    candidate_date = now_et.date()
    candidate_time = now_et.time()

    if is_trading_day(candidate_date) and candidate_time < MARKET_OPEN:
        # Today is a trading day and we haven't hit open yet
        return ET.localize(datetime.combine(candidate_date, MARKET_OPEN))

    # Otherwise, look at subsequent days
    candidate_date += timedelta(days=1)

    # Search forward (max 10 days covers any holiday + weekend combo)
    for _ in range(10):
        if is_trading_day(candidate_date):
            return ET.localize(datetime.combine(candidate_date, MARKET_OPEN))
        candidate_date += timedelta(days=1)

    # Fallback — should never reach here for valid calendar
    return ET.localize(datetime.combine(candidate_date, MARKET_OPEN))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_et(dt: datetime | None) -> datetime:
    """
    Convert a datetime to ET. If None, returns current time in ET.
    If naive, assumes UTC.
    """
    if dt is None:
        return datetime.now(ET)

    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        dt = pytz.utc.localize(dt)

    return dt.astimezone(ET)
