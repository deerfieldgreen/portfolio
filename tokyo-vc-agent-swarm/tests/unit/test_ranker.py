"""Unit tests for the composite ranker node."""

from __future__ import annotations

import pytest

from tokyo_vc_swarm.nodes.ranker import composite_ranker_node
from tokyo_vc_swarm.state import DealScores, DimensionScore, SwarmState


def make_state(deals_specs: list) -> SwarmState:
    deals = []
    for deal_id, dims_spec in deals_specs:
        dims = {
            name: DimensionScore(score=s, weight=w, rationale="r")
            for name, s, w in dims_spec
        }
        deals.append(
            DealScores(
                deal_id=deal_id,
                deal_data={},
                dimensions=dims,
                composite_score=None,
                rank=None,
                rank_explanation=None,
            )
        )
    return SwarmState(deals=deals, global_config={}, ranked_output=None, error=None)


def test_weighted_average():
    # deal-a: (8*1 + 6*2) / (1+2) = 20/3 ≈ 6.667
    state = make_state([("deal-a", [("market", 8.0, 1.0), ("team", 6.0, 2.0)])])
    result = composite_ranker_node(state)
    assert abs(result["deals"][0]["composite_score"] - 20 / 3) < 0.001


def test_rank_order_descending():
    state = make_state([
        ("low", [("market", 3.0, 1.0)]),
        ("high", [("market", 9.0, 1.0)]),
    ])
    result = composite_ranker_node(state)
    assert result["deals"][0]["deal_id"] == "high"
    assert result["deals"][0]["rank"] == 1
    assert result["deals"][1]["rank"] == 2


def test_inverted_dimension_lowers_score(monkeypatch):
    """risk_regulatory invert=True: score=8 should act like effective=2, lowering composite."""
    from tokyo_vc_swarm.nodes import ranker as ranker_mod
    monkeypatch.setattr(
        "tokyo_vc_swarm.nodes.ranker.Config.get_inverted_dimensions",
        lambda: {"risk_regulatory"},
    )
    # risk score=8 → effective=2; market score=8 → effective=8; equal weights
    # composite = (2+8)/2 = 5.0
    state = make_state([("deal-x", [("risk_regulatory", 8.0, 1.0), ("market", 8.0, 1.0)])])
    result = composite_ranker_node(state)
    assert result["deals"][0]["composite_score"] == pytest.approx(5.0)


def test_empty_dimensions_gives_zero():
    state = SwarmState(
        deals=[DealScores(deal_id="empty", deal_data={}, dimensions={},
                          composite_score=None, rank=None, rank_explanation=None)],
        global_config={},
        ranked_output=None,
        error=None,
    )
    result = composite_ranker_node(state)
    assert result["deals"][0]["composite_score"] == 0.0
