"""
Unit tests for src/trading/sigma_detector.py

Tests the trailing stddev computation and sigma event detection logic.
Requirements: 6.1, 6.2, 6.3
"""

import math
import os
import sys

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.trading.sigma_detector import compute_trailing_stddev, detect_sigma_event


# ---------------------------------------------------------------------------
# compute_trailing_stddev tests
# ---------------------------------------------------------------------------


class TestComputeTrailingStddev:
    def test_returns_zero_for_empty_list(self):
        assert compute_trailing_stddev([]) == 0.0

    def test_returns_zero_for_single_value(self):
        assert compute_trailing_stddev([0.05]) == 0.0

    def test_returns_zero_for_fewer_than_2_data_points(self):
        assert compute_trailing_stddev([]) == 0.0
        assert compute_trailing_stddev([1.0]) == 0.0

    def test_correct_sample_stddev_for_known_values(self):
        # For [1, 2, 3, 4, 5]: mean=3, variance=(1+1+0+1+1+4)/(5-1)... let's be exact
        # deviations from mean: -2, -1, 0, 1, 2
        # squared: 4, 1, 0, 1, 4 → sum = 10
        # sample variance = 10/4 = 2.5
        # sample stddev = sqrt(2.5) ≈ 1.5811
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = compute_trailing_stddev(data)
        assert math.isclose(result, math.sqrt(2.5), rel_tol=1e-9)

    def test_uses_last_20_values_only(self):
        # Create 25 values; only last 20 should be used
        data = [100.0] * 5 + [1.0] * 20
        result = compute_trailing_stddev(data)
        # Last 20 values are all 1.0 — stddev should be 0
        assert result == 0.0

    def test_uses_all_values_when_20_or_fewer(self):
        data = [1.0, 3.0]  # mean=2, variance=(1+1)/1=2, stddev=sqrt(2)
        result = compute_trailing_stddev(data)
        assert math.isclose(result, math.sqrt(2.0), rel_tol=1e-9)

    def test_two_data_points(self):
        # [0.0, 1.0]: mean=0.5, sum_sq_diff=(0.25 + 0.25)=0.5, var=0.5/1=0.5
        result = compute_trailing_stddev([0.0, 1.0])
        assert math.isclose(result, math.sqrt(0.5), rel_tol=1e-9)

    def test_constant_values_return_zero(self):
        data = [0.02] * 20
        result = compute_trailing_stddev(data)
        assert math.isclose(result, 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# detect_sigma_event tests
# ---------------------------------------------------------------------------


class TestDetectSigmaEvent:
    def test_returns_none_for_insufficient_data(self):
        # Fewer than 2 trailing data points → stddev is 0 → returns None
        result = detect_sigma_event(5.0, [0.01])
        assert result is None

    def test_returns_none_for_empty_trailing(self):
        result = detect_sigma_event(5.0, [])
        assert result is None

    def test_returns_none_when_stddev_is_zero(self):
        # All same values → stddev = 0, should return None
        result = detect_sigma_event(0.05, [0.01] * 20)
        assert result is None

    def test_returns_none_when_change_below_threshold(self):
        # stddev of [1, -1, 1, -1, ...] is 1.0 (sample)
        trailing = [1.0, -1.0] * 10  # 20 values
        # stddev ≈ 1.026
        # threshold = 2 * stddev ≈ 2.052
        # daily_change = 1.5 → |1.5| < 2.052 → no event
        result = detect_sigma_event(1.5, trailing)
        assert result is None

    def test_triggers_for_large_positive_move(self):
        # Use known constant-ish trailing data with low stddev
        trailing = [0.01, -0.01, 0.005, -0.005, 0.01, -0.01,
                    0.005, -0.005, 0.01, -0.01, 0.005, -0.005,
                    0.01, -0.01, 0.005, -0.005, 0.01, -0.01,
                    0.005, -0.005]
        stddev = compute_trailing_stddev(trailing)
        threshold = 2.0 * stddev
        # A move much larger than threshold
        big_move = threshold + 1.0
        result = detect_sigma_event(big_move, trailing)
        assert result is not None
        assert result["triggered"] is True
        assert result["magnitude"] == big_move
        assert math.isclose(result["threshold_2sigma"], threshold, rel_tol=1e-9)
        assert math.isclose(result["trailing_stddev"], stddev, rel_tol=1e-9)

    def test_triggers_for_large_negative_move(self):
        trailing = [0.01, -0.01, 0.005, -0.005, 0.01, -0.01,
                    0.005, -0.005, 0.01, -0.01, 0.005, -0.005,
                    0.01, -0.01, 0.005, -0.005, 0.01, -0.01,
                    0.005, -0.005]
        stddev = compute_trailing_stddev(trailing)
        threshold = 2.0 * stddev
        big_move = -(threshold + 1.0)
        result = detect_sigma_event(big_move, trailing)
        assert result is not None
        assert result["triggered"] is True
        assert result["magnitude"] == big_move

    def test_does_not_trigger_at_exactly_threshold(self):
        # |change| must be strictly greater than threshold to trigger
        trailing = [0.01, -0.01] * 10
        stddev = compute_trailing_stddev(trailing)
        threshold = 2.0 * stddev
        result = detect_sigma_event(threshold, trailing)
        assert result is None

    def test_custom_threshold_sigmas(self):
        trailing = [0.01, -0.01] * 10
        stddev = compute_trailing_stddev(trailing)
        # Use threshold_sigmas=1.0 — lower bar
        threshold = 1.0 * stddev
        # A move just above 1σ but below 2σ
        move = threshold + 0.001
        result = detect_sigma_event(move, trailing, threshold_sigmas=1.0)
        assert result is not None
        assert result["triggered"] is True
        assert math.isclose(result["threshold_2sigma"], threshold, rel_tol=1e-9)

    def test_event_dict_has_correct_keys(self):
        trailing = [0.01, -0.01] * 10
        stddev = compute_trailing_stddev(trailing)
        threshold = 2.0 * stddev
        big_move = threshold + 0.5
        result = detect_sigma_event(big_move, trailing)
        assert set(result.keys()) == {"triggered", "magnitude", "threshold_2sigma", "trailing_stddev"}
