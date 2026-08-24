# Feature: autonomous-trading-loop, Property 11: Read-only API enforcement
"""
Property-based tests for serve.py — read-only API enforcement in autonomous mode.

Property 11: Read-only API enforcement
For any order_id string, POST /api/accept/<order_id> returns 403.
For any order_id string, POST /api/deny/<order_id> returns 403.
For any ticker string, POST /api/close/<ticker> returns 403.
The response body always contains {"error": "autonomous_mode_active"}.

Also verify that GET endpoints (/api/book, /api/history, /api/pending, /api/alerts)
return 200.

**Validates: Requirements 8.3, 8.5**
"""

from __future__ import annotations

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from serve import app


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate arbitrary order_id strings (non-empty, printable, URL-safe subset)
order_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd"), whitelist_characters="-_"),
    min_size=1,
    max_size=50,
)

# Generate arbitrary ticker strings (uppercase letters + digits, realistic)
ticker_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "N")),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property Tests: POST endpoints return 403 in autonomous mode
# ---------------------------------------------------------------------------


@given(order_id=order_id_strategy)
@settings(max_examples=200)
def test_property11_post_accept_returns_403(order_id: str):
    """
    **Validates: Requirements 8.3, 8.5**

    Property 11: For any order_id string, POST /api/accept/<order_id> returns HTTP 403
    with body containing {"error": "autonomous_mode_active"}.
    """
    with app.test_client() as client:
        response = client.post(f"/api/accept/{order_id}")
        assert response.status_code == 403, (
            f"Expected 403 for POST /api/accept/{order_id}, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"
        assert data.get("error") == "autonomous_mode_active", (
            f"Expected error='autonomous_mode_active', got {data.get('error')!r}"
        )


@given(order_id=order_id_strategy)
@settings(max_examples=200)
def test_property11_post_deny_returns_403(order_id: str):
    """
    **Validates: Requirements 8.3, 8.5**

    Property 11: For any order_id string, POST /api/deny/<order_id> returns HTTP 403
    with body containing {"error": "autonomous_mode_active"}.
    """
    with app.test_client() as client:
        response = client.post(f"/api/deny/{order_id}")
        assert response.status_code == 403, (
            f"Expected 403 for POST /api/deny/{order_id}, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"
        assert data.get("error") == "autonomous_mode_active", (
            f"Expected error='autonomous_mode_active', got {data.get('error')!r}"
        )


@given(ticker=ticker_strategy)
@settings(max_examples=200)
def test_property11_post_close_returns_403(ticker: str):
    """
    **Validates: Requirements 8.3, 8.5**

    Property 11: For any ticker string, POST /api/close/<ticker> returns HTTP 403
    with body containing {"error": "autonomous_mode_active"}.
    """
    with app.test_client() as client:
        response = client.post(f"/api/close/{ticker}")
        assert response.status_code == 403, (
            f"Expected 403 for POST /api/close/{ticker}, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"
        assert data.get("error") == "autonomous_mode_active", (
            f"Expected error='autonomous_mode_active', got {data.get('error')!r}"
        )


# ---------------------------------------------------------------------------
# Property Tests: GET endpoints return 200
# ---------------------------------------------------------------------------


def test_property11_get_book_returns_200():
    """
    **Validates: Requirements 8.5**

    Property 11: GET /api/book returns HTTP 200 with valid JSON.
    """
    with app.test_client() as client:
        response = client.get("/api/book")
        assert response.status_code == 200, (
            f"Expected 200 for GET /api/book, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"


def test_property11_get_history_returns_200():
    """
    **Validates: Requirements 8.5**

    Property 11: GET /api/history returns HTTP 200 with valid JSON.
    """
    with app.test_client() as client:
        response = client.get("/api/history")
        assert response.status_code == 200, (
            f"Expected 200 for GET /api/history, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"


def test_property11_get_pending_returns_200():
    """
    **Validates: Requirements 8.5**

    Property 11: GET /api/pending returns HTTP 200 with valid JSON.
    """
    with app.test_client() as client:
        response = client.get("/api/pending")
        assert response.status_code == 200, (
            f"Expected 200 for GET /api/pending, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"


def test_property11_get_alerts_returns_200():
    """
    **Validates: Requirements 8.5**

    Property 11: GET /api/alerts returns HTTP 200 with valid JSON.
    """
    with app.test_client() as client:
        response = client.get("/api/alerts")
        assert response.status_code == 200, (
            f"Expected 200 for GET /api/alerts, got {response.status_code}"
        )
        data = response.get_json()
        assert data is not None, "Response body should be valid JSON"
