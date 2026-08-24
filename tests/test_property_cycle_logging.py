# Feature: operational-reliability, Property 13: Pipeline Cycle Logging Completeness
"""
Property-based tests for pipeline cycle logging completeness.

For all completed pipeline cycles (any sequence of phases), the cycle log file
SHALL contain:
1. A cycle_id (string, ISO timestamp format)
2. A trigger_source
3. One entry per executed phase (phases array with name, duration_s, outcome)
4. A summary entry with total_duration_s, proposals_generated, trades_booked, exit_code

Validates: Requirements 14.1, 14.2, 14.3
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from src.data_platform.cycle_logger import (
    log_cycle_start,
    log_phase_complete,
    log_cycle_complete,
    _get_cycle_log_path,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

phase_names = st.lists(
    st.sampled_from(["data_refresh", "proposals", "debate", "risk_gate", "pm_decision"]),
    min_size=1,
    max_size=5,
    unique=True,
)

durations = st.lists(
    st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=5,
)

proposals = st.integers(min_value=0, max_value=20)
trades = st.integers(min_value=0, max_value=10)
exit_code = st.sampled_from([0, 1])
trigger_source = st.sampled_from(["launchd", "manual"])


# ---------------------------------------------------------------------------
# Property 13: Pipeline Cycle Logging Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    phases=phase_names,
    durs=durations,
    props=proposals,
    trds=trades,
    ec=exit_code,
    ts=trigger_source,
)
def test_property_13_pipeline_cycle_logging_completeness(
    phases: list[str],
    durs: list[float],
    props: int,
    trds: int,
    ec: int,
    ts: str,
):
    """
    **Validates: Requirements 14.1, 14.2, 14.3**

    Property 13: Pipeline Cycle Logging Completeness — For all completed
    pipeline cycles (any sequence of phases), the cycle log file SHALL contain
    a cycle_id, trigger_source, one entry per executed phase, and a summary
    with total_duration_s, proposals_generated, trades_booked, exit_code.
    """
    # Align durations list length to phases list length
    effective_durs = durs[: len(phases)]
    # If durations list is shorter than phases, extend with a default
    while len(effective_durs) < len(phases):
        effective_durs.append(1.0)

    cycle_id = None
    try:
        # 1. Start cycle
        cycle_id = log_cycle_start(ts)

        # 2. Log each phase
        for phase, dur in zip(phases, effective_durs):
            log_phase_complete(cycle_id, phase, dur, "success")

        # 3. Complete cycle
        total_dur = sum(effective_durs)
        log_cycle_complete(cycle_id, total_dur, props, trds, ec)

        # 4. Read the resulting JSON file
        path = _get_cycle_log_path(cycle_id)
        assert path.exists(), f"Cycle log file does not exist: {path}"

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 5. Assertions

        # cycle_id matches and is ISO timestamp format
        assert data["cycle_id"] == cycle_id
        assert "T" in data["cycle_id"]
        # ISO format: YYYY-MM-DDTHH:MM:SS (19 chars)
        assert len(data["cycle_id"]) == 19

        # trigger_source matches
        assert data["trigger_source"] == ts

        # phases array length matches number of executed phases
        assert len(data["phases"]) == len(phases)

        # Each phase has required fields (name, duration_s, outcome)
        for i, phase_entry in enumerate(data["phases"]):
            assert "name" in phase_entry, f"Phase {i} missing 'name'"
            assert "duration_s" in phase_entry, f"Phase {i} missing 'duration_s'"
            assert "outcome" in phase_entry, f"Phase {i} missing 'outcome'"
            assert phase_entry["name"] == phases[i]
            assert isinstance(phase_entry["duration_s"], (int, float))
            assert phase_entry["outcome"] == "success"

        # Summary has required fields
        assert data["summary"] is not None
        summary = data["summary"]
        assert "total_duration_s" in summary
        assert "proposals_generated" in summary
        assert "trades_booked" in summary
        assert "exit_code" in summary
        assert summary["proposals_generated"] == props
        assert summary["trades_booked"] == trds
        assert summary["exit_code"] == ec

    finally:
        # Clean up test files after each test
        if cycle_id is not None:
            path = _get_cycle_log_path(cycle_id)
            if path.exists():
                os.remove(path)
