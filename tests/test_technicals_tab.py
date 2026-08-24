"""
Unit tests for the Technicals tab rendering logic (Task 8.1).

Feature: dashboard-autonomous-revamp
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

Tests the Python equivalents of the client-side JavaScript logic for:
- Normalizing scores to composite (0-100)
- Trend direction normalization
- Momentum classification normalization
- Sector derivation from proposal_id
- Ticker derivation from proposal_id
- Sector grouping with averages
- P&L cross-reference with book positions
- Weakening technical flag (score < 40 on active positions)
- Sorting by composite score descending
"""

from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Python equivalents of JS functions from the revamped renderTechnical()
# ---------------------------------------------------------------------------

def normalize_trend_direction(alignment: str | None) -> str:
    """Maps trend_alignment to trend_direction (up/down/sideways)."""
    if not alignment:
        return "sideways"
    a = alignment.lower()
    if a in ("aligned", "bullish", "up"):
        return "up"
    if a in ("opposed", "bearish", "down"):
        return "down"
    return "sideways"


def normalize_momentum(regime: str | None) -> str:
    """Maps momentum_regime to momentum classification (strong/moderate/weak)."""
    if not regime:
        return "weak"
    r = regime.lower()
    if "strong" in r:
        return "strong"
    if "moderate" in r or "consolidation" in r or "inflection" in r:
        return "moderate"
    return "weak"


SECTOR_MAP = {
    "consdisc": "Consumer Discretionary",
    "consstaples": "Consumer Staples",
    "commsvcs": "Communication Services",
    "energy": "Energy",
    "tech": "Technology",
    "healthcare": "Healthcare",
    "financials": "Financials",
    "industrials": "Industrials",
    "materials": "Materials",
    "utilities": "Utilities",
    "realestate": "Real Estate",
    "commodities": "Commodities",
    "asia": "Asia",
    "westerneurope": "Western Europe",
}


def derive_sector(score_data: dict) -> str:
    """Derives sector from score data, falling back to proposal_id parsing."""
    if score_data.get("sector"):
        return score_data["sector"]
    pid = score_data.get("proposal_id", "")
    # Remove tech_ prefix, then split
    stripped = re.sub(r"^tech_", "", pid)
    parts = stripped.split("_")
    if len(parts) >= 2:
        sector_raw = parts[1]
        mapped = SECTOR_MAP.get(sector_raw.lower())
        if mapped:
            return mapped
        # Capitalize raw sector name
        return sector_raw.replace("_", " ").strip().title() or "Other"
    return "Other"


def derive_ticker(score_data: dict) -> str:
    """Derives ticker from score data."""
    if score_data.get("ticker"):
        return score_data["ticker"].upper()
    pid = score_data.get("proposal_id", "")
    parts = pid.split("_")
    # Find last alphabetical part that looks like a ticker (1-5 chars, not a keyword)
    keywords = {"fund", "macro", "tech", "short", "long"}
    for p in reversed(parts):
        if re.match(r"^[a-zA-Z]{1,5}$", p) and p.lower() not in keywords:
            return p.upper()
    # Fallback
    stripped = re.sub(r"^(tech_)?(fund_|macro_)?", "", pid)
    first = stripped.split("_")[0].upper()
    return first if first else "—"


def normalize_scores(raw_scores: list[dict], positions: list[dict]) -> list[dict]:
    """
    Normalizes raw score objects into the unified structure used by the
    Technicals tab ranked table.
    """
    # Build position map
    position_map = {}
    for p in positions:
        if p.get("ticker") and p.get("status") == "active":
            position_map[p["ticker"].upper()] = p

    normalized = []
    for s in raw_scores:
        if s.get("technical_score") is None or s.get("error"):
            continue
        composite = s.get("composite_score") if s.get("composite_score") is not None else (s.get("technical_score", 0)) * 10
        ticker = derive_ticker(s)
        sector = derive_sector(s)
        trend_dir = s.get("trend_direction") or normalize_trend_direction(s.get("trend_alignment"))
        momentum = s.get("momentum") or normalize_momentum(s.get("momentum_regime"))
        position = position_map.get(ticker)
        pnl = position["combined_pnl_pct"] if position else None
        has_position = position is not None
        is_weakening = composite < 40 and has_position

        normalized.append({
            "ticker": ticker,
            "composite_score": composite,
            "trend_direction": trend_dir,
            "momentum": momentum,
            "sector": sector,
            "pnl": pnl,
            "has_position": has_position,
            "is_weakening": is_weakening,
        })

    # Sort by composite score descending
    normalized.sort(key=lambda x: x["composite_score"], reverse=True)
    return normalized


def group_by_sector(normalized_scores: list[dict]) -> list[dict]:
    """Groups scores by sector and computes sector averages."""
    groups = {}
    for s in normalized_scores:
        sector = s["sector"]
        if sector not in groups:
            groups[sector] = []
        groups[sector].append(s)

    result = []
    for name, items in groups.items():
        avg = sum(i["composite_score"] for i in items) / len(items) if items else 0
        result.append({"name": name, "items": items, "avg": avg})
    result.sort(key=lambda x: x["avg"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrendDirectionNormalization:
    def test_aligned_maps_to_up(self):
        assert normalize_trend_direction("aligned") == "up"

    def test_bullish_maps_to_up(self):
        assert normalize_trend_direction("bullish") == "up"

    def test_opposed_maps_to_down(self):
        assert normalize_trend_direction("opposed") == "down"

    def test_bearish_maps_to_down(self):
        assert normalize_trend_direction("bearish") == "down"

    def test_neutral_maps_to_sideways(self):
        assert normalize_trend_direction("neutral") == "sideways"

    def test_none_maps_to_sideways(self):
        assert normalize_trend_direction(None) == "sideways"

    def test_case_insensitive(self):
        assert normalize_trend_direction("ALIGNED") == "up"
        assert normalize_trend_direction("Opposed") == "down"


class TestMomentumNormalization:
    def test_strong_keyword(self):
        assert normalize_momentum("strong_downtrend_with_early_counter-trend_reversal_signals") == "strong"

    def test_moderate_keyword(self):
        assert normalize_momentum("moderate_uptrend") == "moderate"

    def test_consolidation_maps_to_moderate(self):
        assert normalize_momentum("weak_trend_consolidation") == "moderate"

    def test_inflection_maps_to_moderate(self):
        assert normalize_momentum("early_inflection_within_downtrend") == "moderate"

    def test_no_trend_maps_to_weak(self):
        assert normalize_momentum("no_trend_stalling_uptrend") == "weak"

    def test_none_maps_to_weak(self):
        assert normalize_momentum(None) == "weak"


class TestSectorDerivation:
    def test_explicit_sector_field(self):
        score = {"sector": "Technology", "proposal_id": "anything"}
        assert derive_sector(score) == "Technology"

    def test_fund_consdisc_proposal(self):
        score = {"proposal_id": "tech_fund_consdisc_2026-08-08_2118"}
        assert derive_sector(score) == "Consumer Discretionary"

    def test_fund_energy_proposal(self):
        score = {"proposal_id": "tech_fund_energy_20260808_vlo_short"}
        assert derive_sector(score) == "Energy"

    def test_macro_commodities_proposal(self):
        score = {"proposal_id": "tech_macro_commodities_2026-08-08T21:50"}
        assert derive_sector(score) == "Commodities"

    def test_macro_asia_proposal(self):
        score = {"proposal_id": "tech_macro_asia_japan_2026-08-08T21:45"}
        assert derive_sector(score) == "Asia"

    def test_macro_westerneurope_proposal(self):
        score = {"proposal_id": "tech_macro_westerneurope_20260808t2156"}
        assert derive_sector(score) == "Western Europe"

    def test_empty_proposal_id(self):
        score = {"proposal_id": ""}
        assert derive_sector(score) == "Other"


class TestTickerDerivation:
    def test_explicit_ticker_field(self):
        score = {"ticker": "AAPL", "proposal_id": "anything"}
        assert derive_ticker(score) == "AAPL"

    def test_ticker_from_proposal_nflx(self):
        score = {"proposal_id": "tech_fund_commsvcs_2026-08-08_nflx"}
        assert derive_ticker(score) == "NFLX"

    def test_ticker_from_proposal_vlo(self):
        score = {"proposal_id": "tech_fund_energy_20260808_vlo_short"}
        assert derive_ticker(score) == "VLO"

    def test_ticker_from_proposal_japan(self):
        score = {"proposal_id": "tech_macro_asia_japan_2026-08-08T21:45"}
        assert derive_ticker(score) == "JAPAN"


class TestNormalizeScores:
    def test_composite_score_from_technical_score(self):
        scores = [{"technical_score": 6, "proposal_id": "tech_fund_energy_20260808_vlo_short"}]
        result = normalize_scores(scores, [])
        assert result[0]["composite_score"] == 60

    def test_explicit_composite_score_used_when_present(self):
        scores = [{"technical_score": 6, "composite_score": 75, "proposal_id": "tech_fund_energy_20260808_vlo_short"}]
        result = normalize_scores(scores, [])
        assert result[0]["composite_score"] == 75

    def test_sorted_descending(self):
        scores = [
            {"technical_score": 3, "proposal_id": "tech_fund_consdisc_2026_ticker1"},
            {"technical_score": 8, "proposal_id": "tech_fund_energy_2026_ticker2"},
            {"technical_score": 5, "proposal_id": "tech_macro_asia_2026_ticker3"},
        ]
        result = normalize_scores(scores, [])
        assert result[0]["composite_score"] == 80
        assert result[1]["composite_score"] == 50
        assert result[2]["composite_score"] == 30

    def test_pnl_annotation_when_in_book(self):
        scores = [{"technical_score": 7, "ticker": "VLO", "proposal_id": "tech_fund_energy_vlo"}]
        positions = [{"ticker": "VLO", "status": "active", "combined_pnl_pct": 0.05}]
        result = normalize_scores(scores, positions)
        assert result[0]["pnl"] == 0.05
        assert result[0]["has_position"] is True

    def test_no_pnl_annotation_when_not_in_book(self):
        scores = [{"technical_score": 7, "ticker": "VLO", "proposal_id": "tech_fund_energy_vlo"}]
        positions = [{"ticker": "AAPL", "status": "active", "combined_pnl_pct": 0.05}]
        result = normalize_scores(scores, positions)
        assert result[0]["pnl"] is None
        assert result[0]["has_position"] is False

    def test_weakening_technical_flag(self):
        scores = [{"technical_score": 3, "ticker": "VLO", "proposal_id": "tech_fund_energy_vlo"}]
        positions = [{"ticker": "VLO", "status": "active", "combined_pnl_pct": -0.02}]
        result = normalize_scores(scores, positions)
        assert result[0]["is_weakening"] is True

    def test_not_weakening_when_score_above_40(self):
        scores = [{"technical_score": 5, "ticker": "VLO", "proposal_id": "tech_fund_energy_vlo"}]
        positions = [{"ticker": "VLO", "status": "active", "combined_pnl_pct": -0.02}]
        result = normalize_scores(scores, positions)
        assert result[0]["is_weakening"] is False

    def test_not_weakening_when_no_position(self):
        scores = [{"technical_score": 2, "ticker": "VLO", "proposal_id": "tech_fund_energy_vlo"}]
        positions = []
        result = normalize_scores(scores, positions)
        assert result[0]["is_weakening"] is False

    def test_skips_error_scores(self):
        scores = [
            {"technical_score": 7, "proposal_id": "valid", "ticker": "VLO"},
            {"technical_score": 5, "proposal_id": "invalid", "error": "timeout"},
        ]
        result = normalize_scores(scores, [])
        assert len(result) == 1

    def test_skips_null_technical_score(self):
        scores = [
            {"technical_score": 7, "proposal_id": "valid", "ticker": "VLO"},
            {"technical_score": None, "proposal_id": "missing"},
        ]
        result = normalize_scores(scores, [])
        assert len(result) == 1


class TestSectorGrouping:
    def test_groups_by_sector(self):
        normalized = [
            {"ticker": "A", "composite_score": 80, "sector": "Energy"},
            {"ticker": "B", "composite_score": 60, "sector": "Technology"},
            {"ticker": "C", "composite_score": 70, "sector": "Energy"},
        ]
        groups = group_by_sector(normalized)
        sector_names = [g["name"] for g in groups]
        assert "Energy" in sector_names
        assert "Technology" in sector_names

    def test_sector_average_computed(self):
        normalized = [
            {"ticker": "A", "composite_score": 80, "sector": "Energy"},
            {"ticker": "C", "composite_score": 60, "sector": "Energy"},
        ]
        groups = group_by_sector(normalized)
        energy_group = next(g for g in groups if g["name"] == "Energy")
        assert energy_group["avg"] == 70.0

    def test_sectors_sorted_by_average_descending(self):
        normalized = [
            {"ticker": "A", "composite_score": 80, "sector": "Energy"},
            {"ticker": "B", "composite_score": 30, "sector": "Technology"},
            {"ticker": "C", "composite_score": 60, "sector": "Energy"},
        ]
        groups = group_by_sector(normalized)
        assert groups[0]["name"] == "Energy"
        assert groups[1]["name"] == "Technology"

    def test_empty_scores(self):
        groups = group_by_sector([])
        assert groups == []

    def test_scores_without_sector_go_to_other(self):
        normalized = [
            {"ticker": "A", "composite_score": 50, "sector": "Other"},
        ]
        groups = group_by_sector(normalized)
        assert groups[0]["name"] == "Other"
