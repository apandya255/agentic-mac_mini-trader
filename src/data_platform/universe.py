"""
Universe configuration for the Agentic AI Trading System.

Defines all tickers in the tradeable universe, their GICS sector classification,
hedge pair mappings, and utility functions for lookups.

Universe (per spec):
- All S&P 500 single names (~503 securities)
- 11 GICS sector ETFs
- 20 MSCI country ETFs (13 DM + 7 EM)
- Commodities: gold, gold miners, silver, silver miners, copper, oil & gas
  (aluminum dropped per partner update)
- Broad hedge instruments: RSP, EFA, EEM, ACWI
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# GICS Sectors
# ---------------------------------------------------------------------------

class GICSSector(str, Enum):
    ENERGY = "energy"
    MATERIALS = "materials"
    INDUSTRIALS = "industrials"
    CONSUMER_DISCRETIONARY = "consumer_discretionary"
    CONSUMER_STAPLES = "consumer_staples"
    HEALTH_CARE = "health_care"
    FINANCIALS = "financials"
    INFORMATION_TECHNOLOGY = "information_technology"
    COMMUNICATION_SERVICES = "communication_services"
    UTILITIES = "utilities"
    REAL_ESTATE = "real_estate"


# ---------------------------------------------------------------------------
# Sector ETFs and their equal-weight hedges
# ---------------------------------------------------------------------------

SECTOR_ETFS: dict[GICSSector, dict[str, str]] = {
    GICSSector.ENERGY:                  {"cap_weight": "XLE",  "equal_weight": "RSPG"},
    GICSSector.MATERIALS:               {"cap_weight": "XLB",  "equal_weight": "RSPM"},
    GICSSector.INDUSTRIALS:             {"cap_weight": "XLI",  "equal_weight": "RSPI"},
    GICSSector.CONSUMER_DISCRETIONARY:  {"cap_weight": "XLY",  "equal_weight": "RSPD"},
    GICSSector.CONSUMER_STAPLES:        {"cap_weight": "XLP",  "equal_weight": "RSPS"},
    GICSSector.HEALTH_CARE:             {"cap_weight": "XLV",  "equal_weight": "RSPH"},
    GICSSector.FINANCIALS:              {"cap_weight": "XLF",  "equal_weight": "RSPF"},
    GICSSector.INFORMATION_TECHNOLOGY:  {"cap_weight": "XLK",  "equal_weight": "RSPT"},
    GICSSector.COMMUNICATION_SERVICES:  {"cap_weight": "XLC",  "equal_weight": "RSPC"},
    GICSSector.UTILITIES:               {"cap_weight": "XLU",  "equal_weight": "RSPU"},
    GICSSector.REAL_ESTATE:             {"cap_weight": "XLRE", "equal_weight": "RSPR"},
}

# Reverse lookup: cap-weight ETF ticker -> sector
_CAP_WEIGHT_TO_SECTOR: dict[str, GICSSector] = {
    v["cap_weight"]: k for k, v in SECTOR_ETFS.items()
}

# Reverse lookup: equal-weight ETF ticker -> sector
_EW_TO_SECTOR: dict[str, GICSSector] = {
    v["equal_weight"]: k for k, v in SECTOR_ETFS.items()
}


# ---------------------------------------------------------------------------
# Country ETFs
# ---------------------------------------------------------------------------

class MarketClass(str, Enum):
    DEVELOPED = "DM"
    EMERGING = "EM"


@dataclass(frozen=True)
class CountryETF:
    ticker: str
    country: str
    market_class: MarketClass


COUNTRY_ETFS: list[CountryETF] = [
    # Developed Markets (13)
    CountryETF("EWJ", "Japan", MarketClass.DEVELOPED),
    CountryETF("EWG", "Germany", MarketClass.DEVELOPED),
    CountryETF("EWU", "United Kingdom", MarketClass.DEVELOPED),
    CountryETF("EWA", "Australia", MarketClass.DEVELOPED),
    CountryETF("EWC", "Canada", MarketClass.DEVELOPED),
    CountryETF("EWH", "Hong Kong", MarketClass.DEVELOPED),
    CountryETF("EWS", "Singapore", MarketClass.DEVELOPED),
    CountryETF("EWL", "Switzerland", MarketClass.DEVELOPED),
    CountryETF("EWD", "Sweden", MarketClass.DEVELOPED),
    CountryETF("EWN", "Netherlands", MarketClass.DEVELOPED),
    CountryETF("EWI", "Italy", MarketClass.DEVELOPED),
    CountryETF("EWP", "Spain", MarketClass.DEVELOPED),
    CountryETF("EWQ", "France", MarketClass.DEVELOPED),
    # Emerging Markets (7)
    CountryETF("EWZ", "Brazil", MarketClass.EMERGING),
    CountryETF("FXI", "China", MarketClass.EMERGING),
    CountryETF("EWY", "South Korea", MarketClass.EMERGING),
    CountryETF("EWT", "Taiwan", MarketClass.EMERGING),
    CountryETF("EWW", "Mexico", MarketClass.EMERGING),
    CountryETF("EWM", "Malaysia", MarketClass.EMERGING),
    CountryETF("INDA", "India", MarketClass.EMERGING),
]

COUNTRY_ETF_TICKERS: set[str] = {c.ticker for c in COUNTRY_ETFS}

_COUNTRY_ETF_MAP: dict[str, CountryETF] = {c.ticker: c for c in COUNTRY_ETFS}


# ---------------------------------------------------------------------------
# Commodities & Miners
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommodityVehicle:
    ticker: str
    commodity: str
    vehicle_type: str  # "spot_proxy" | "miner_etf" | "producer_etf"


COMMODITY_VEHICLES: list[CommodityVehicle] = [
    CommodityVehicle("GLD", "gold", "spot_proxy"),
    CommodityVehicle("GDX", "gold", "miner_etf"),
    CommodityVehicle("SLV", "silver", "spot_proxy"),
    CommodityVehicle("SIL", "silver", "miner_etf"),
    CommodityVehicle("COPX", "copper", "miner_etf"),
    CommodityVehicle("USO", "oil", "spot_proxy"),
    CommodityVehicle("XOP", "oil_gas", "producer_etf"),
]

COMMODITY_TICKERS: set[str] = {c.ticker for c in COMMODITY_VEHICLES}


# ---------------------------------------------------------------------------
# Broad Hedge Instruments
# ---------------------------------------------------------------------------

BROAD_HEDGES = {
    "RSP": "Equal-weight S&P 500 (hedge for sector ETF trades)",
    "EFA": "MSCI EAFE (hedge for DM country ETF trades)",
    "EEM": "MSCI Emerging Markets (hedge for EM country ETF trades)",
    "ACWI": "MSCI All Country World (universal hedge)",
}


# ---------------------------------------------------------------------------
# S&P 500 Constituents — Sector Mapping
# (Representative sample; full list loaded dynamically or from a file)
# ---------------------------------------------------------------------------

# This maps ticker -> GICSSector for all S&P 500 names.
# In production, this would be loaded from a maintained file or API.
# Here we provide the structure + a bootstrap function.

_SP500_SECTOR_MAP: dict[str, GICSSector] = {}


def load_sp500_from_wiki() -> dict[str, GICSSector]:
    """
    Fetch current S&P 500 constituents and their GICS sectors from Wikipedia.
    Returns a dict mapping ticker -> GICSSector.
    Falls back to empty dict if fetch fails.
    """
    global _SP500_SECTOR_MAP
    if _SP500_SECTOR_MAP:
        return _SP500_SECTOR_MAP

    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            header=0,
        )
        df = tables[0]
        # Wikipedia columns: Symbol, Security, GICS Sector, ...
        sector_map_raw = {
            "Energy": GICSSector.ENERGY,
            "Materials": GICSSector.MATERIALS,
            "Industrials": GICSSector.INDUSTRIALS,
            "Consumer Discretionary": GICSSector.CONSUMER_DISCRETIONARY,
            "Consumer Staples": GICSSector.CONSUMER_STAPLES,
            "Health Care": GICSSector.HEALTH_CARE,
            "Financials": GICSSector.FINANCIALS,
            "Information Technology": GICSSector.INFORMATION_TECHNOLOGY,
            "Communication Services": GICSSector.COMMUNICATION_SERVICES,
            "Utilities": GICSSector.UTILITIES,
            "Real Estate": GICSSector.REAL_ESTATE,
        }
        for _, row in df.iterrows():
            ticker = str(row["Symbol"]).replace(".", "-")  # BRK.B -> BRK-B
            gics = str(row["GICS Sector"])
            if gics in sector_map_raw:
                _SP500_SECTOR_MAP[ticker] = sector_map_raw[gics]
    except Exception:
        pass  # Graceful degradation — empty map, caller handles

    return _SP500_SECTOR_MAP


# ---------------------------------------------------------------------------
# Hedge Pair Resolution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HedgePair:
    """Represents the hedge for a given ticker."""
    primary_ticker: str
    primary_direction: str  # "long" or "short"
    hedge_ticker: str
    hedge_direction: str  # opposite of primary


def get_hedge(ticker: str, direction: str = "long") -> Optional[HedgePair]:
    """
    Given a ticker and direction, return the correct hedge pair.

    Rules (from spec):
    - Single name in a GICS sector -> hedge with equal-weight sector ETF
    - Sector ETF (cap-weight) -> hedge with RSP
    - DM country ETF -> hedge with EFA or ACWI
    - EM country ETF -> hedge with EEM or ACWI
    - Commodity vehicle -> hedge with ACWI (default; PM has discretion)

    Returns None if ticker is not in the known universe.
    """
    opposite = "short" if direction == "long" else "long"

    # Check if it's a cap-weight sector ETF
    if ticker in _CAP_WEIGHT_TO_SECTOR:
        return HedgePair(
            primary_ticker=ticker,
            primary_direction=direction,
            hedge_ticker="RSP",
            hedge_direction=opposite,
        )

    # Check if it's a country ETF
    if ticker in _COUNTRY_ETF_MAP:
        country_etf = _COUNTRY_ETF_MAP[ticker]
        if country_etf.market_class == MarketClass.DEVELOPED:
            hedge_ticker = "EFA"
        else:
            hedge_ticker = "EEM"
        return HedgePair(
            primary_ticker=ticker,
            primary_direction=direction,
            hedge_ticker=hedge_ticker,
            hedge_direction=opposite,
        )

    # Check if it's a commodity vehicle
    if ticker in COMMODITY_TICKERS:
        return HedgePair(
            primary_ticker=ticker,
            primary_direction=direction,
            hedge_ticker="ACWI",
            hedge_direction=opposite,
        )

    # Check if it's an S&P 500 single name
    sp500 = load_sp500_from_wiki() if not _SP500_SECTOR_MAP else _SP500_SECTOR_MAP
    if ticker in sp500:
        sector = sp500[ticker]
        hedge_ticker = SECTOR_ETFS[sector]["equal_weight"]
        return HedgePair(
            primary_ticker=ticker,
            primary_direction=direction,
            hedge_ticker=hedge_ticker,
            hedge_direction=opposite,
        )

    return None


def get_sector_for_ticker(ticker: str) -> Optional[GICSSector]:
    """Return the GICS sector for an S&P 500 name, or None if not found."""
    sp500 = load_sp500_from_wiki() if not _SP500_SECTOR_MAP else _SP500_SECTOR_MAP
    return sp500.get(ticker)


# ---------------------------------------------------------------------------
# Full Universe Ticker List (for data fetching)
# ---------------------------------------------------------------------------

class Universe:
    """
    Provides access to the full tradeable universe and hedge resolution.

    Usage:
        u = Universe()
        u.load()  # fetches S&P 500 constituents
        all_tickers = u.all_tickers()
        hedge = u.get_hedge("XOM", "long")
    """

    def __init__(self):
        self._loaded = False

    def load(self) -> None:
        """Load S&P 500 constituents (requires internet on first call)."""
        load_sp500_from_wiki()
        self._loaded = True

    @property
    def sp500_tickers(self) -> list[str]:
        sp500 = load_sp500_from_wiki() if not _SP500_SECTOR_MAP else _SP500_SECTOR_MAP
        return sorted(sp500.keys())

    @property
    def sector_etf_tickers(self) -> list[str]:
        return sorted(_CAP_WEIGHT_TO_SECTOR.keys())

    @property
    def equal_weight_etf_tickers(self) -> list[str]:
        return sorted(_EW_TO_SECTOR.keys())

    @property
    def country_etf_tickers(self) -> list[str]:
        return sorted(COUNTRY_ETF_TICKERS)

    @property
    def commodity_tickers(self) -> list[str]:
        return sorted(COMMODITY_TICKERS)

    @property
    def hedge_tickers(self) -> list[str]:
        return sorted(BROAD_HEDGES.keys())

    def all_tickers(self) -> list[str]:
        """All unique tickers in the universe (for price fetching)."""
        tickers = set()
        tickers.update(self.sp500_tickers)
        tickers.update(self.sector_etf_tickers)
        tickers.update(self.equal_weight_etf_tickers)
        tickers.update(self.country_etf_tickers)
        tickers.update(self.commodity_tickers)
        tickers.update(self.hedge_tickers)
        return sorted(tickers)

    def get_hedge(self, ticker: str, direction: str = "long") -> Optional[HedgePair]:
        """Resolve the hedge pair for a given ticker and direction."""
        return get_hedge(ticker, direction)

    def get_sector(self, ticker: str) -> Optional[GICSSector]:
        """Get the GICS sector for an S&P 500 constituent."""
        return get_sector_for_ticker(ticker)

    def sector_constituents(self, sector: GICSSector) -> list[str]:
        """Return all S&P 500 tickers in a given sector."""
        sp500 = load_sp500_from_wiki() if not _SP500_SECTOR_MAP else _SP500_SECTOR_MAP
        return sorted(t for t, s in sp500.items() if s == sector)
