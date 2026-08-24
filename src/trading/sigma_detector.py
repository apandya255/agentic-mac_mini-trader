"""
Sigma Event Detector — detects outsized price moves based on trailing volatility.

Computes trailing 20-day sample standard deviation and triggers an event when
the absolute daily change exceeds a configurable multiple (default 2σ) of
that trailing volatility.

Requirements: 6.1, 6.2, 6.3
"""

import math


def compute_trailing_stddev(daily_changes: list[float]) -> float:
    """
    Compute sample standard deviation of the last 20 daily_change_pct values.

    Uses Bessel's correction (n-1 denominator) for sample stddev.
    Returns 0.0 if fewer than 2 data points are available.

    Args:
        daily_changes: List of daily percentage changes (e.g. [0.02, -0.01, ...]).

    Returns:
        Sample standard deviation of the last 20 values, or 0.0 if insufficient data.
    """
    data = daily_changes[-20:]
    n = len(data)
    if n < 2:
        return 0.0
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / (n - 1)
    return math.sqrt(variance)


def detect_sigma_event(
    daily_change_pct: float,
    trailing_20d_changes: list[float],
    threshold_sigmas: float = 2.0,
) -> dict | None:
    """
    Detect if today's move exceeds the threshold-sigma level.

    Args:
        daily_change_pct: Today's daily percentage change.
        trailing_20d_changes: Historical daily changes for stddev computation.
        threshold_sigmas: Number of standard deviations for the trigger (default 2.0).

    Returns:
        Event dict with keys (triggered, magnitude, threshold_2sigma, trailing_stddev)
        if |daily_change_pct| > threshold_sigmas × trailing_stddev.
        Returns None if no event triggered or if stddev is 0.
    """
    stddev = compute_trailing_stddev(trailing_20d_changes)
    if stddev == 0.0:
        return None

    threshold = threshold_sigmas * stddev
    if abs(daily_change_pct) > threshold:
        return {
            "triggered": True,
            "magnitude": daily_change_pct,
            "threshold_2sigma": threshold,
            "trailing_stddev": stddev,
        }
    return None
