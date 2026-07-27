"""
Macro Data Service for the Agentic AI Trading System.

Fetches economic indicators from FRED (free API) and caches locally.
Used by Macro Agents to track growth, inflation, policy, and external
accounts across regions.

Per spec, macro agents track:
- GDP, PMIs, labor
- Inflation and central bank reaction function
- Fiscal picture and debt sustainability
- External accounts, BoP, reserves, terms of trade, capital flows
- FX valuation, politics, geopolitical risk

FRED covers US and many international indicators. For non-US data,
agents would supplement with IMF/World Bank APIs in production.

Usage:
    from data_platform.macro_data import MacroDataService
    mds = MacroDataService(fred_api_key="your_key")
    gdp = mds.get_indicator("GDP", lookback_quarters=8)
    curve = mds.yield_curve()
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "macro.db"


# ---------------------------------------------------------------------------
# FRED Series Catalog
# ---------------------------------------------------------------------------

# Mapping of human-readable indicator names to FRED series IDs.
# Organized by category for easy lookup.

FRED_SERIES: dict[str, dict[str, str]] = {
    # US Growth & Activity
    "US_GDP": {"series_id": "GDP", "description": "US Real GDP (Quarterly, SAAR)", "frequency": "Q"},
    "US_GDP_GROWTH": {"series_id": "A191RL1Q225SBEA", "description": "US Real GDP Growth Rate", "frequency": "Q"},
    "US_PMI_MFG": {"series_id": "MANEMP", "description": "US Manufacturing Employment (proxy)", "frequency": "M"},
    "US_ISM_MFG": {"series_id": "NAPM", "description": "ISM Manufacturing PMI", "frequency": "M"},
    "US_ISM_SERVICES": {"series_id": "NMFCI", "description": "ISM Non-Manufacturing (Services)", "frequency": "M"},
    "US_INDUSTRIAL_PROD": {"series_id": "INDPRO", "description": "US Industrial Production Index", "frequency": "M"},
    "US_RETAIL_SALES": {"series_id": "RSAFS", "description": "US Retail Sales (Total)", "frequency": "M"},
    "US_HOUSING_STARTS": {"series_id": "HOUST", "description": "US Housing Starts", "frequency": "M"},

    # US Labor
    "US_UNEMPLOYMENT": {"series_id": "UNRATE", "description": "US Unemployment Rate", "frequency": "M"},
    "US_NONFARM_PAYROLLS": {"series_id": "PAYEMS", "description": "US Nonfarm Payrolls (Total)", "frequency": "M"},
    "US_INITIAL_CLAIMS": {"series_id": "ICSA", "description": "US Initial Jobless Claims", "frequency": "W"},
    "US_JOLTS_OPENINGS": {"series_id": "JTSJOL", "description": "US Job Openings (JOLTS)", "frequency": "M"},
    "US_WAGE_GROWTH": {"series_id": "CES0500000003", "description": "US Avg Hourly Earnings", "frequency": "M"},

    # US Inflation
    "US_CPI": {"series_id": "CPIAUCSL", "description": "US CPI (All Urban, SA)", "frequency": "M"},
    "US_CPI_CORE": {"series_id": "CPILFESL", "description": "US Core CPI (ex Food & Energy)", "frequency": "M"},
    "US_PCE": {"series_id": "PCEPI", "description": "US PCE Price Index", "frequency": "M"},
    "US_PCE_CORE": {"series_id": "PCEPILFE", "description": "US Core PCE Price Index", "frequency": "M"},
    "US_PPI": {"series_id": "PPIACO", "description": "US PPI (All Commodities)", "frequency": "M"},
    "US_BREAKEVEN_5Y": {"series_id": "T5YIE", "description": "5-Year Breakeven Inflation", "frequency": "D"},
    "US_BREAKEVEN_10Y": {"series_id": "T10YIE", "description": "10-Year Breakeven Inflation", "frequency": "D"},

    # US Rates & Policy
    "FED_FUNDS_RATE": {"series_id": "FEDFUNDS", "description": "Effective Federal Funds Rate", "frequency": "M"},
    "FED_FUNDS_UPPER": {"series_id": "DFEDTARU", "description": "Fed Funds Target Upper", "frequency": "D"},
    "SOFR": {"series_id": "SOFR", "description": "Secured Overnight Financing Rate", "frequency": "D"},
    "US_2Y": {"series_id": "DGS2", "description": "US 2-Year Treasury Yield", "frequency": "D"},
    "US_5Y": {"series_id": "DGS5", "description": "US 5-Year Treasury Yield", "frequency": "D"},
    "US_10Y": {"series_id": "DGS10", "description": "US 10-Year Treasury Yield", "frequency": "D"},
    "US_30Y": {"series_id": "DGS30", "description": "US 30-Year Treasury Yield", "frequency": "D"},
    "US_2S10S": {"series_id": "T10Y2Y", "description": "10Y-2Y Treasury Spread", "frequency": "D"},
    "US_3M10Y": {"series_id": "T10Y3M", "description": "10Y-3M Treasury Spread", "frequency": "D"},

    # US Fiscal & Debt
    "US_FEDERAL_DEBT": {"series_id": "GFDEBTN", "description": "US Federal Debt (Total)", "frequency": "Q"},
    "US_DEFICIT_GDP": {"series_id": "FYFSGDA188S", "description": "US Federal Surplus/Deficit as % GDP", "frequency": "A"},

    # Financial Conditions & Credit
    "US_HY_SPREAD": {"series_id": "BAMLH0A0HYM2", "description": "ICE BofA US HY OAS", "frequency": "D"},
    "US_IG_SPREAD": {"series_id": "BAMLC0A0CM", "description": "ICE BofA US Corp IG OAS", "frequency": "D"},
    "CHICAGO_FCI": {"series_id": "NFCI", "description": "Chicago Fed Nat'l Financial Conditions Index", "frequency": "W"},
    "VIX": {"series_id": "VIXCLS", "description": "CBOE VIX", "frequency": "D"},

    # Dollar & FX
    "DXY_BROAD": {"series_id": "DTWEXBGS", "description": "Trade Weighted US Dollar (Broad)", "frequency": "D"},

    # Commodities (from FRED)
    "WTI_CRUDE": {"series_id": "DCOILWTICO", "description": "WTI Crude Oil Spot", "frequency": "D"},
    "GOLD_PRICE": {"series_id": "GOLDAMGBD228NLBM", "description": "Gold Fixing Price (London)", "frequency": "D"},

    # International
    "EU_CPI": {"series_id": "CP0000EZ19M086NEST", "description": "Euro Area HICP", "frequency": "M"},
    "CHINA_GDP": {"series_id": "MKTGDPCNA646NWDB", "description": "China GDP (Current USD)", "frequency": "A"},
    "JAPAN_CPI": {"series_id": "JPNCPIALLMINMEI", "description": "Japan CPI", "frequency": "M"},
    "UK_CPI": {"series_id": "GBRCPIALLMINMEI", "description": "UK CPI", "frequency": "M"},
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorReading:
    """A single economic indicator with context."""
    name: str
    series_id: str
    description: str
    latest_value: float
    latest_date: str
    prior_value: Optional[float]
    change: Optional[float]  # latest - prior
    change_pct: Optional[float]
    frequency: str


@dataclass(frozen=True)
class YieldCurve:
    """US Treasury yield curve snapshot."""
    as_of_date: str
    us_2y: Optional[float]
    us_5y: Optional[float]
    us_10y: Optional[float]
    us_30y: Optional[float]
    spread_2s10s: Optional[float]
    spread_3m10y: Optional[float]
    curve_shape: str  # "normal" | "flat" | "inverted"


# ---------------------------------------------------------------------------
# Macro Data Service
# ---------------------------------------------------------------------------

class MacroDataService:
    """
    Fetches and caches macroeconomic data from FRED.

    Requires a FRED API key (free at https://fred.stlouisfed.org/docs/api/api_key.html).
    Falls back gracefully if no key is provided (returns empty results).
    """

    def __init__(self, fred_api_key: Optional[str] = None, db_path: Optional[Path] = None):
        self.fred_api_key = fred_api_key
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._fred = None

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS macro_series (
                    series_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    value REAL,
                    PRIMARY KEY (series_id, date)
                )
            """)

    def _get_fred(self):
        """Lazy-init FRED client."""
        if self._fred is None and self.fred_api_key:
            from fredapi import Fred
            self._fred = Fred(api_key=self.fred_api_key)
        return self._fred

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    def refresh(self, indicators: Optional[list[str]] = None, lookback_days: int = 365) -> int:
        """
        Fetch/update indicators from FRED and cache locally.

        Args:
            indicators: List of indicator names (keys in FRED_SERIES).
                        If None, fetches all defined indicators.
            lookback_days: How far back to fetch.

        Returns:
            Number of data points stored.
        """
        fred = self._get_fred()
        if fred is None:
            return 0

        if indicators is None:
            indicators = list(FRED_SERIES.keys())

        total = 0
        start = date.today() - timedelta(days=lookback_days)

        for name in indicators:
            if name not in FRED_SERIES:
                continue

            series_id = FRED_SERIES[name]["series_id"]
            try:
                data = fred.get_series(series_id, observation_start=start.isoformat())
                if data is None or data.empty:
                    continue

                rows = []
                for dt, val in data.items():
                    if val is not None and not (isinstance(val, float) and val != val):
                        rows.append((series_id, dt.strftime("%Y-%m-%d"), float(val)))

                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO macro_series (series_id, date, value) VALUES (?, ?, ?)",
                        rows,
                    )
                total += len(rows)

            except Exception:
                continue

        return total

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_indicator(
        self,
        name: str,
        lookback_periods: int = 12,
    ) -> Optional[IndicatorReading]:
        """
        Get the latest reading for a named indicator.

        Args:
            name: Indicator name (key in FRED_SERIES).
            lookback_periods: Not used for latest, but kept for interface consistency.

        Returns:
            IndicatorReading with latest and prior values, or None if no data.
        """
        if name not in FRED_SERIES:
            return None

        info = FRED_SERIES[name]
        series_id = info["series_id"]

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT date, value FROM macro_series 
                   WHERE series_id = ? ORDER BY date DESC LIMIT 2""",
                (series_id,),
            ).fetchall()

        if not rows:
            return None

        latest_date, latest_value = rows[0]
        prior_value = rows[1][1] if len(rows) > 1 else None
        change = (latest_value - prior_value) if prior_value is not None else None
        change_pct = (change / abs(prior_value)) if (prior_value and prior_value != 0) else None

        return IndicatorReading(
            name=name,
            series_id=series_id,
            description=info["description"],
            latest_value=latest_value,
            latest_date=latest_date,
            prior_value=prior_value,
            change=round(change, 4) if change is not None else None,
            change_pct=round(change_pct, 4) if change_pct is not None else None,
            frequency=info["frequency"],
        )

    def get_series(self, name: str, lookback_days: int = 365) -> pd.Series:
        """
        Get a full time series for an indicator from local cache.

        Returns a pandas Series indexed by date.
        """
        if name not in FRED_SERIES:
            return pd.Series(dtype=float)

        series_id = FRED_SERIES[name]["series_id"]
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                """SELECT date, value FROM macro_series 
                   WHERE series_id = ? AND date >= ? ORDER BY date""",
                conn,
                params=(series_id, cutoff),
            )

        if df.empty:
            return pd.Series(dtype=float, name=name)

        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["value"].rename(name)

    # ------------------------------------------------------------------
    # Composite Views
    # ------------------------------------------------------------------

    def yield_curve(self) -> YieldCurve:
        """
        Get current US Treasury yield curve snapshot.
        Reads from local cache (call refresh() first to populate).
        """
        def latest_val(name: str) -> Optional[float]:
            reading = self.get_indicator(name)
            return reading.latest_value if reading else None

        us_2y = latest_val("US_2Y")
        us_5y = latest_val("US_5Y")
        us_10y = latest_val("US_10Y")
        us_30y = latest_val("US_30Y")
        spread_2s10s = latest_val("US_2S10S")
        spread_3m10y = latest_val("US_3M10Y")

        # Determine curve shape
        if spread_2s10s is not None:
            if spread_2s10s < -0.1:
                shape = "inverted"
            elif spread_2s10s < 0.3:
                shape = "flat"
            else:
                shape = "normal"
        else:
            shape = "unknown"

        # Get as-of date
        reading = self.get_indicator("US_10Y")
        as_of = reading.latest_date if reading else date.today().isoformat()

        return YieldCurve(
            as_of_date=as_of,
            us_2y=us_2y,
            us_5y=us_5y,
            us_10y=us_10y,
            us_30y=us_30y,
            spread_2s10s=spread_2s10s,
            spread_3m10y=spread_3m10y,
            curve_shape=shape,
        )

    def inflation_snapshot(self) -> dict:
        """Get current inflation indicators."""
        indicators = ["US_CPI", "US_CPI_CORE", "US_PCE_CORE", "US_BREAKEVEN_5Y", "US_BREAKEVEN_10Y"]
        result = {}
        for name in indicators:
            reading = self.get_indicator(name)
            if reading:
                result[name] = {
                    "value": reading.latest_value,
                    "date": reading.latest_date,
                    "change": reading.change,
                }
        return result

    def labor_snapshot(self) -> dict:
        """Get current labor market indicators."""
        indicators = ["US_UNEMPLOYMENT", "US_NONFARM_PAYROLLS", "US_INITIAL_CLAIMS", "US_JOLTS_OPENINGS", "US_WAGE_GROWTH"]
        result = {}
        for name in indicators:
            reading = self.get_indicator(name)
            if reading:
                result[name] = {
                    "value": reading.latest_value,
                    "date": reading.latest_date,
                    "change": reading.change,
                }
        return result

    def credit_snapshot(self) -> dict:
        """Get current credit/financial conditions indicators."""
        indicators = ["US_HY_SPREAD", "US_IG_SPREAD", "CHICAGO_FCI", "VIX"]
        result = {}
        for name in indicators:
            reading = self.get_indicator(name)
            if reading:
                result[name] = {
                    "value": reading.latest_value,
                    "date": reading.latest_date,
                    "change": reading.change,
                }
        return result

    def available_indicators(self) -> list[str]:
        """List all defined indicator names."""
        return sorted(FRED_SERIES.keys())

    def data_freshness(self) -> dict[str, str]:
        """Return the latest date available for each series in the cache."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT series_id, MAX(date) FROM macro_series GROUP BY series_id"
            ).fetchall()

        # Map series_id back to indicator name
        id_to_name = {v["series_id"]: k for k, v in FRED_SERIES.items()}
        return {id_to_name.get(r[0], r[0]): r[1] for r in rows}
