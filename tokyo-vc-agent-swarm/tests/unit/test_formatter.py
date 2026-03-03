"""Unit tests for the output formatter node."""

from __future__ import annotations

from tokyo_vc_swarm.nodes.formatter import output_formatter_node
from tokyo_vc_swarm.state import DealScores, DimensionScore, SwarmState


def make_state_with_ranked(deal_id: str, composite: float, rank: int) -> SwarmState:
    dims = {
        "market": DimensionScore(score=8.0, weight=1.0, rationale="Good market"),
        "traction": DimensionScore(score=9.0, weight=1.5, rationale="Strong traction"),
        "risk_regulatory": DimensionScore(score=4.0, weight=0.8, rationale="Some risk"),
    }
    deal = DealScores(
        deal_id=deal_id,
        deal_data={},
        dimensions=dims,
        composite_score=composite,
        rank=rank,
        rank_explanation=None,
    )
    return SwarmState(deals=[deal], global_config={}, ranked_output=None, error=None)


def test_formatter_populates_ranked_output():
    state = make_state_with_ranked("deal-1", 7.5, 1)
    result = output_formatter_node(state)
    assert result["ranked_output"] is not None
    assert len(result["ranked_output"]) == 1
    out = result["ranked_output"][0]
    assert out["rank"] == 1
    assert out["deal_id"] == "deal-1"
    assert out["composite_score"] == 7.5
    assert "traction" in out["dimensions"]


def test_formatter_includes_explanation():
    state = make_state_with_ranked("deal-2", 6.0, 1)
    result = output_formatter_node(state)
    explanation = result["ranked_output"][0]["explanation"]
    assert "Rank #1" in explanation
    assert "6.00" in explanation


def test_formatter_sets_rank_explanation_on_deal():
    state = make_state_with_ranked("deal-3", 8.0, 1)
    result = output_formatter_node(state)
    assert result["deals"][0]["rank_explanation"] is not None
