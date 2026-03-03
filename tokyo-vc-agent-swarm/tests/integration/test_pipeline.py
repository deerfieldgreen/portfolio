"""Integration tests: full pipeline run with mock LLM and no ClickHouse."""

from __future__ import annotations

import os
import pytest

# Provide dummy API key so Config.validate() passes without a real key
os.environ.setdefault("NOVITA_API_KEY", "test-key")


from tokyo_vc_swarm.pipeline import DealScoringPipeline

SAMPLE_DEALS = [
    {
        "deal_id": "deal-alpha",
        "company": "AlphaAI",
        "sector": "B2B SaaS",
        "stage": "Series A",
        "arr_usd": 2_000_000,
        "growth_yoy_pct": 180,
        "team_size": 12,
        "japan_customers": True,
        "round_size_usd": 8_000_000,
    },
    {
        "deal_id": "deal-beta",
        "company": "BetaFintech",
        "sector": "Fintech",
        "stage": "Seed",
        "arr_usd": 300_000,
        "growth_yoy_pct": 90,
        "team_size": 5,
        "japan_customers": False,
        "round_size_usd": 2_000_000,
    },
    {
        "deal_id": "deal-gamma",
        "company": "GammaRobotics",
        "sector": "DeepTech",
        "stage": "Pre-seed",
        "arr_usd": 0,
        "growth_yoy_pct": None,
        "team_size": 3,
        "japan_customers": False,
        "round_size_usd": 500_000,
    },
]


@pytest.fixture
def pipeline():
    return DealScoringPipeline()


def test_pipeline_run_mock_returns_ranked_list(pipeline):
    ranked = pipeline.run(SAMPLE_DEALS, mock=True)
    assert len(ranked) == 3
    # Ranks are 1-indexed and sequential
    assert [d["rank"] for d in ranked] == [1, 2, 3]


def test_pipeline_run_mock_composite_scores_valid(pipeline):
    ranked = pipeline.run(SAMPLE_DEALS, mock=True)
    for deal in ranked:
        assert 0.0 <= deal["composite_score"] <= 10.0


def test_pipeline_run_mock_all_dimensions_present(pipeline):
    ranked = pipeline.run(SAMPLE_DEALS, mock=True)
    expected_dims = {"market", "team", "product", "traction", "syndication_fit",
                     "risk_regulatory", "japan_fit"}
    for deal in ranked:
        assert set(deal["dimensions"].keys()) == expected_dims


def test_pipeline_run_mock_explanations_non_empty(pipeline):
    ranked = pipeline.run(SAMPLE_DEALS, mock=True)
    for deal in ranked:
        assert len(deal["explanation"]) > 10


def test_pipeline_stream_mock_yields_events(pipeline):
    events = list(pipeline.stream(SAMPLE_DEALS, mock=True))
    types = [e["type"] for e in events]
    assert "status" in types
    assert "complete" in types
    complete_event = next(e for e in events if e["type"] == "complete")
    assert len(complete_event["ranked_output"]) == 3


def test_pipeline_weight_overrides_applied(pipeline):
    """Overriding traction weight to 5.0 should keep composite valid."""
    ranked = pipeline.run(SAMPLE_DEALS, weight_overrides={"traction": 5.0}, mock=True)
    assert len(ranked) == 3
    for deal in ranked:
        assert deal["dimensions"]["traction"]["weight"] == 5.0
