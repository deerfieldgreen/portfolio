"""Output formatter node: builds RankedDeal list with natural-language explanations."""

from __future__ import annotations

import logging

from ..state import RankedDeal, SwarmState

logger = logging.getLogger(__name__)

_DIM_LABELS = {
    "market": "market attractiveness",
    "team": "team quality",
    "product": "product/moat",
    "traction": "traction",
    "syndication_fit": "syndication fit",
    "risk_regulatory": "low regulatory risk",
    "japan_fit": "Japan/Tokyo fit",
}


def _build_explanation(deal) -> str:
    """Build a natural-language explanation of rank drivers."""
    dims = deal["dimensions"]
    if not dims:
        return "No dimension scores available."

    # Sort by effective contribution (weight * score) descending
    scored = sorted(
        dims.items(),
        key=lambda kv: kv[1]["weight"] * kv[1]["score"],
        reverse=True,
    )
    strengths = [_DIM_LABELS.get(k, k) for k, _ in scored[:2]]
    weaknesses = [_DIM_LABELS.get(k, k) for k, _ in scored[-1:]]

    strength_str = " and ".join(strengths)
    weakness_str = weaknesses[0] if weaknesses else "—"

    return (
        f"Rank #{deal['rank']} (composite {deal['composite_score']:.2f}/10): "
        f"strong {strength_str} drive this result"
        + (f", despite moderate {weakness_str}." if weakness_str != "—" else ".")
    )


def output_formatter_node(state: SwarmState) -> SwarmState:
    """
    Convert ranked deals into RankedDeal output list with explanations.
    """
    ranked_output = []
    for deal in state["deals"]:
        explanation = _build_explanation(deal)
        deal["rank_explanation"] = explanation
        ranked_output.append(
            RankedDeal(
                rank=deal["rank"],
                deal_id=deal["deal_id"],
                composite_score=deal["composite_score"] or 0.0,
                dimensions=deal["dimensions"],
                explanation=explanation,
            )
        )

    state["ranked_output"] = ranked_output
    logger.info("Formatter: formatted %d ranked deals", len(ranked_output))
    return state
