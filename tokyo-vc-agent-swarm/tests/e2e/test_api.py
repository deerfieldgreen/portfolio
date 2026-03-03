"""E2E tests for the FastAPI endpoints using TestClient."""

from __future__ import annotations

import os
import pytest

os.environ.setdefault("NOVITA_API_KEY", "test-key")

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

SAMPLE_DEALS = [
    {
        "deal_id": "e2e-deal-1",
        "company": "TestCo",
        "sector": "SaaS",
        "stage": "Series A",
        "arr_usd": 1_500_000,
    },
    {
        "deal_id": "e2e-deal-2",
        "company": "AnotherCo",
        "sector": "Fintech",
        "stage": "Seed",
        "arr_usd": 200_000,
    },
]


@pytest.fixture
def client():
    """Return TestClient with mocked ClickHouse so no DB is needed."""
    with patch("tokyo_vc_swarm.api._ch_writer", None):
        from tokyo_vc_swarm.api import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_score_mock_returns_ranked_list(client):
    r = client.post("/score", json={"deals": SAMPLE_DEALS, "mock": True, "persist": False})
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert len(body["ranked_deals"]) == 2
    assert body["ranked_deals"][0]["rank"] == 1


def test_score_mock_all_dimensions_present(client):
    r = client.post("/score", json={"deals": SAMPLE_DEALS, "mock": True, "persist": False})
    dims = body = r.json()["ranked_deals"][0]["dimensions"]
    expected = {"market", "team", "product", "traction", "syndication_fit",
                "risk_regulatory", "japan_fit"}
    assert set(dims.keys()) == expected


def test_score_empty_deals_rejected(client):
    r = client.post("/score", json={"deals": [], "mock": True, "persist": False})
    assert r.status_code == 422


def test_rankings_no_clickhouse_returns_503(client):
    r = client.get("/rankings")
    assert r.status_code == 503
