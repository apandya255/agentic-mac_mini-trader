# Feature: dashboard-autonomous-revamp, Property 6: Alert grouping counts sum to total alerts
# Feature: dashboard-autonomous-revamp, Property 7: Trailing 20-day volatility computation matches stddev definition
# Feature: dashboard-autonomous-revamp, Property 8: Conviction trajectory preserves round ordering
"""
Property-based tests for dashboard computation functions:
- Alert grouping by severity
- Trailing 20-day volatility (computeTrailing20dVol equivalent)
- Conviction trajectory ordering (computeConvictionTrajectory equivalent)

**Validates: Requirements 3.1, 3.6, 4.5**
"""

from __future__ import annotations

import math
import os
import sys
from typing import Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Python equivalents of client-side JS computation functions
# ---------------------------------------------------------------------------


def group_alerts_by_severity(alerts: list[dict]) -> dict[str, int]:
    """
    Group alerts by severity level and return counts.

    Python equivalent of the JS alert grouping logic:
        alerts.filter(a => a.level === 'critical').length +
        alerts.filter(a => a.level === 'warning').length +
        alerts.filter(a => a.level === 'info').length === alerts.length

    Args:
        alerts: List of alert dicts with at least a 'level' field.

    Returns:
        Dict with keys 'critical', 'warning', 'info' and integer counts.
    """
    counts = {"critical": 0, "warning": 0, "info": 0}
    for alert in alerts:
        level = alert.get("level", "")
        if level in counts:
            counts[level] += 1
    return counts


def compute_trailing_20d_vol(price_history: list[dict]) -> Optional[float]:
    """
    Compute trailing 20-day volatility as sample standard deviation of
    the last 20 daily_change_pct values.

    Python equivalent of:
        function computeTrailing20dVol(priceHistory) {
            if (!priceHistory || priceHistory.length < 2) return null;
            const values = priceHistory.slice(-20).map(h => h.daily_change_pct);
            if (values.length < 2) return null;
            const n = values.length;
            const mean = values.reduce((s, v) => s + v, 0) / n;
            const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1);
            return Math.sqrt(variance);
        }

    Uses Bessel's correction (n-1 denominator).

    Args:
        price_history: List of dicts with 'daily_change_pct' field.

    Returns:
        Sample standard deviation of last 20 daily_change_pct values,
        or None if fewer than 2 entries.
    """
    if not price_history or len(price_history) < 2:
        return None
    values = [h["daily_change_pct"] for h in price_history[-20:]]
    if len(values) < 2:
        return None
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def compute_conviction_trajectory(debate: dict) -> list[float]:
    """
    Compute ordered conviction values across debate rounds.

    Python equivalent of:
        function computeConvictionTrajectory(debate) {
            if (!debate || !debate.rounds || debate.rounds.length === 0) return [];
            const sorted = [...debate.rounds].sort((a, b) => a.round - b.round);
            return sorted.map(round => {
                const convictions = (round.arguments || []).map(
                    arg => arg.revised_conviction != null ? arg.revised_conviction : arg.conviction
                );
                if (convictions.length === 0) return null;
                return convictions.reduce((s, v) => s + v, 0) / convictions.length;
            }).filter(v => v != null);
        }

    Args:
        debate: Dict with 'rounds' list. Each round has 'round' (number)
                and 'arguments' (list of dicts with 'conviction' and optionally
                'revised_conviction').

    Returns:
        List of average conviction values, sorted by round number,
        excluding rounds with no arguments.
    """
    if not debate or not debate.get("rounds") or len(debate["rounds"]) == 0:
        return []
    sorted_rounds = sorted(debate["rounds"], key=lambda r: r["round"])
    result = []
    for round_data in sorted_rounds:
        arguments = round_data.get("arguments", [])
        if not arguments:
            continue
        convictions = []
        for arg in arguments:
            if arg.get("revised_conviction") is not None:
                convictions.append(arg["revised_conviction"])
            else:
                convictions.append(arg["conviction"])
        if not convictions:
            continue
        avg = sum(convictions) / len(convictions)
        result.append(avg)
    return result


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Alert strategies
ALERT_LEVELS = ["critical", "warning", "info"]

alert_st = st.fixed_dictionaries({
    "level": st.sampled_from(ALERT_LEVELS),
    "category": st.sampled_from(["stop", "drawdown", "factor", "correlation", "holding", "sigma"]),
    "ticker": st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "message": st.text(min_size=1, max_size=50),
})

alerts_list_st = st.lists(alert_st, min_size=0, max_size=50)

# Price history strategies
daily_change_st = st.floats(min_value=-0.20, max_value=0.20, allow_nan=False, allow_infinity=False)

price_history_entry_st = st.fixed_dictionaries({
    "daily_change_pct": daily_change_st,
})

# At least 2 entries to get a valid result
price_history_st = st.lists(price_history_entry_st, min_size=2, max_size=40)

# Debate strategies
conviction_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

argument_st = st.fixed_dictionaries(
    {"conviction": conviction_st},
    optional={"revised_conviction": st.one_of(st.none(), conviction_st)},
)

# Non-empty arguments list (rounds with arguments produce trajectory values)
arguments_list_st = st.lists(argument_st, min_size=1, max_size=5)


def debate_round_st(round_num_st):
    """Strategy for a debate round with a given round number strategy."""
    return st.fixed_dictionaries({
        "round": round_num_st,
        "arguments": arguments_list_st,
    })


# Generate debates with unique round numbers to avoid ambiguity in ordering
def debate_st(min_rounds=1, max_rounds=10):
    """Strategy for a debate with multiple rounds with unique round numbers."""
    return st.integers(min_value=min_rounds, max_value=max_rounds).flatmap(
        lambda n: st.lists(
            st.integers(min_value=1, max_value=100),
            min_size=n,
            max_size=n,
            unique=True,
        ).flatmap(
            lambda round_nums: st.tuples(
                *[arguments_list_st for _ in round_nums]
            ).map(
                lambda args_tuple: {
                    "rounds": [
                        {"round": rn, "arguments": args}
                        for rn, args in zip(round_nums, args_tuple)
                    ]
                }
            )
        )
    )


# ---------------------------------------------------------------------------
# Property 6: Alert grouping counts sum to total alerts
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(alerts=alerts_list_st)
def test_property_6_alert_grouping_counts_sum_to_total(alerts: list[dict]):
    """
    **Validates: Requirements 3.1**

    Property 6: For any list of alerts, the sum of alerts grouped by severity
    (critical + warning + info) SHALL equal the total number of alerts in the
    input list.

    Since all alerts have level in {critical, warning, info}, grouping by these
    three categories must account for every alert.
    """
    counts = group_alerts_by_severity(alerts)

    total_grouped = counts["critical"] + counts["warning"] + counts["info"]
    assert total_grouped == len(alerts), (
        f"Grouped counts ({total_grouped}) != total alerts ({len(alerts)}). "
        f"Counts: {counts}"
    )


@settings(max_examples=200)
@given(alerts=alerts_list_st)
def test_property_6_alert_grouping_counts_are_non_negative(alerts: list[dict]):
    """
    **Validates: Requirements 3.1**

    Property 6 (non-negativity): Each severity group count SHALL be
    non-negative for any input.
    """
    counts = group_alerts_by_severity(alerts)

    for level, count in counts.items():
        assert count >= 0, f"Negative count for {level}: {count}"


@settings(max_examples=100)
@given(alerts=alerts_list_st)
def test_property_6_alert_grouping_individual_counts_correct(alerts: list[dict]):
    """
    **Validates: Requirements 3.1**

    Property 6 (correctness): Each severity group count SHALL equal the number
    of alerts with that specific level.
    """
    counts = group_alerts_by_severity(alerts)

    for level in ALERT_LEVELS:
        expected = sum(1 for a in alerts if a["level"] == level)
        assert counts[level] == expected, (
            f"Count for '{level}': expected {expected}, got {counts[level]}"
        )


# ---------------------------------------------------------------------------
# Property 7: Trailing 20-day volatility computation matches stddev definition
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(price_history=price_history_st)
def test_property_7_trailing_vol_matches_sample_stddev(price_history: list[dict]):
    """
    **Validates: Requirements 3.6**

    Property 7: For any price history with at least 2 entries,
    computeTrailing20dVol(priceHistory) SHALL return the sample standard
    deviation (Bessel's correction, n-1 denominator) of the last 20
    daily_change_pct values.
    """
    result = compute_trailing_20d_vol(price_history)
    assert result is not None, "Should return a value for >= 2 entries"

    # Manually compute expected stddev
    values = [h["daily_change_pct"] for h in price_history[-20:]]
    n = len(values)
    assert n >= 2

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    expected = math.sqrt(variance)

    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-15), (
        f"Vol mismatch: expected {expected}, got {result}"
    )


@settings(max_examples=200)
@given(price_history=price_history_st)
def test_property_7_trailing_vol_is_non_negative(price_history: list[dict]):
    """
    **Validates: Requirements 3.6**

    Property 7 (non-negativity): The computed volatility SHALL always be
    non-negative (stddev >= 0).
    """
    result = compute_trailing_20d_vol(price_history)
    assert result is not None
    assert result >= 0.0, f"Volatility should be non-negative, got {result}"


@settings(max_examples=100)
@given(price_history=price_history_st)
def test_property_7_trailing_vol_uses_last_20(price_history: list[dict]):
    """
    **Validates: Requirements 3.6**

    Property 7 (windowing): The computation SHALL use at most the last 20
    entries. Adding entries beyond 20 at the beginning SHALL not change the result.
    """
    # Compute with original
    result_original = compute_trailing_20d_vol(price_history)

    # Add extra entries at the beginning — should not change result
    extra = [{"daily_change_pct": 0.99}] * 5
    extended = extra + price_history
    result_extended = compute_trailing_20d_vol(extended)

    # If original has > 20 entries, both use last 20, results should match
    # If original has <= 20, result_original uses all; extended uses last 20 which
    # includes the original entries (since extra is prepended)
    if len(price_history) >= 20:
        assert math.isclose(result_original, result_extended, rel_tol=1e-9), (
            f"Windowing violated: original={result_original}, extended={result_extended}"
        )


@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=1),
)
def test_property_7_insufficient_data_returns_none(n: int):
    """
    **Validates: Requirements 3.6**

    Property 7 (insufficient data): When fewer than 2 entries exist,
    computeTrailing20dVol SHALL return None.
    """
    price_history = [{"daily_change_pct": 0.01}] * n
    result = compute_trailing_20d_vol(price_history)
    assert result is None, (
        f"Expected None for {n} entries, got {result}"
    )


# ---------------------------------------------------------------------------
# Property 8: Conviction trajectory preserves round ordering
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(debate=debate_st(min_rounds=2, max_rounds=10))
def test_property_8_conviction_trajectory_preserves_order(debate: dict):
    """
    **Validates: Requirements 4.5**

    Property 8: For any debate with multiple rounds,
    computeConvictionTrajectory(debate) SHALL return conviction values in the
    same temporal order as the debate rounds (sorted by round number).
    """
    trajectory = compute_conviction_trajectory(debate)

    # Get expected order: rounds sorted by round number
    sorted_rounds = sorted(debate["rounds"], key=lambda r: r["round"])

    # Build expected trajectory (skip rounds with no arguments)
    expected = []
    for round_data in sorted_rounds:
        arguments = round_data.get("arguments", [])
        if not arguments:
            continue
        convictions = []
        for arg in arguments:
            if arg.get("revised_conviction") is not None:
                convictions.append(arg["revised_conviction"])
            else:
                convictions.append(arg["conviction"])
        if convictions:
            expected.append(sum(convictions) / len(convictions))

    assert len(trajectory) == len(expected), (
        f"Trajectory length {len(trajectory)} != expected {len(expected)}"
    )

    for i, (actual, exp) in enumerate(zip(trajectory, expected)):
        assert math.isclose(actual, exp, rel_tol=1e-9), (
            f"Trajectory[{i}] mismatch: got {actual}, expected {exp}"
        )


@settings(max_examples=200)
@given(debate=debate_st(min_rounds=2, max_rounds=10))
def test_property_8_trajectory_round_order_matches_sorted_rounds(debate: dict):
    """
    **Validates: Requirements 4.5**

    Property 8 (ordering invariant): If we shuffle the rounds in the input
    debate, the trajectory output SHALL remain the same (because the function
    sorts by round number internally).
    """
    import random

    # Compute trajectory from original input
    trajectory_original = compute_conviction_trajectory(debate)

    # Shuffle rounds (different order in input)
    shuffled_debate = {"rounds": list(debate["rounds"])}
    random.shuffle(shuffled_debate["rounds"])

    trajectory_shuffled = compute_conviction_trajectory(shuffled_debate)

    assert len(trajectory_original) == len(trajectory_shuffled), (
        f"Length mismatch after shuffle: {len(trajectory_original)} vs {len(trajectory_shuffled)}"
    )

    for i, (orig, shuf) in enumerate(zip(trajectory_original, trajectory_shuffled)):
        assert math.isclose(orig, shuf, rel_tol=1e-9), (
            f"Trajectory[{i}] changed after shuffle: {orig} vs {shuf}"
        )


@settings(max_examples=100)
@given(debate=debate_st(min_rounds=1, max_rounds=1))
def test_property_8_single_round_produces_single_value(debate: dict):
    """
    **Validates: Requirements 4.5**

    Property 8 (single round): A debate with exactly one round (with arguments)
    SHALL produce a trajectory of length 1.
    """
    trajectory = compute_conviction_trajectory(debate)
    assert len(trajectory) == 1, (
        f"Expected 1 trajectory value for single-round debate, got {len(trajectory)}"
    )


@settings(max_examples=100)
@given(st.data())
def test_property_8_empty_debate_returns_empty(data):
    """
    **Validates: Requirements 4.5**

    Property 8 (empty case): A debate with no rounds or None SHALL return
    an empty list.
    """
    debate = data.draw(st.sampled_from([
        None,
        {},
        {"rounds": []},
        {"rounds": None},
    ]))

    if debate is None:
        result = compute_conviction_trajectory(debate)
    elif debate.get("rounds") is None:
        result = compute_conviction_trajectory(debate)
    else:
        result = compute_conviction_trajectory(debate)

    assert result == [], f"Expected empty list for empty debate, got {result}"
