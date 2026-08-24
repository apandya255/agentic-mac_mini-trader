# Feature: operational-reliability, Property 11: Factor Beta Alert Thresholds
"""
Property-based tests for factor beta alert thresholds.

Property 11: For all beta values, correct alert level emitted
(warning iff |beta| > 0.4, critical iff |beta| > 0.6).

**Validates: Requirements 10.3, 10.4**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.trading.factor_beta import get_alert_level, BETA_WARNING_THRESHOLD, BETA_CRITICAL_THRESHOLD


@settings(max_examples=200)
@given(beta=st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_property_11_factor_beta_alert_thresholds(beta: float):
    """
    **Validates: Requirements 10.3, 10.4**

    Property 11: For all float beta values in [-2.0, 2.0]:
      - |beta| <= 0.4 -> get_alert_level returns None
      - 0.4 < |beta| <= 0.6 -> get_alert_level returns "warning"
      - |beta| > 0.6 -> get_alert_level returns "critical"
    """
    abs_beta = abs(beta)
    result = get_alert_level(beta)

    if abs_beta > BETA_CRITICAL_THRESHOLD:
        assert result == "critical", (
            f"Expected 'critical' for |beta|={abs_beta:.4f} > {BETA_CRITICAL_THRESHOLD}, "
            f"but got {result!r}"
        )
    elif abs_beta > BETA_WARNING_THRESHOLD:
        assert result == "warning", (
            f"Expected 'warning' for {BETA_WARNING_THRESHOLD} < |beta|={abs_beta:.4f} <= {BETA_CRITICAL_THRESHOLD}, "
            f"but got {result!r}"
        )
    else:
        assert result is None, (
            f"Expected None for |beta|={abs_beta:.4f} <= {BETA_WARNING_THRESHOLD}, "
            f"but got {result!r}"
        )
