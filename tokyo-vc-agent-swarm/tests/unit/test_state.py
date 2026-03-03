"""Unit tests for state TypedDicts and composite ranker math."""

from __future__ import annotations

import pytest

from tokyo_vc_swarm.state import DealScores, DimensionScore, RankedDeal, SwarmState


def make_deal(deal_id: str, scores: dict) -> DealScores:
    dims = {
        dim: DimensionScore(score=score, weight=1.0, rationale="test")
        for dim, score in scores.items()
    }
    return DealScores(
        deal_id=deal_id,
        deal_data={},
        dimensions=dims,
        composite_score=None,
        rank=None,
        rank_explanation=None,
    )


def test_dimension_score_fields():
    ds = DimensionScore(score=7.5, weight=1.2, rationale="Good market")
    assert ds["score"] == 7.5
    assert ds["weight"] == 1.2
    assert ds["rationale"] == "Good market"


def test_deal_scores_fields():
    deal = make_deal("deal-1", {"market": 8.0})
    assert deal["deal_id"] == "deal-1"
    assert deal["dimensions"]["market"]["score"] == 8.0
    assert deal["composite_score"] is None


def test_swarm_state_fields():
    state = SwarmState(
        deals=[make_deal("d1", {"market": 5.0})],
        global_config={"market": 1.0},
        ranked_output=None,
        error=None,
    )
    assert len(state["deals"]) == 1
    assert state["error"] is None
