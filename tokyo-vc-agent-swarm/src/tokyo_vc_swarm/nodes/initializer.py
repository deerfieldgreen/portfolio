"""Initializer node: normalises raw input deals into SwarmState."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from ..state import DealScores, SwarmState

logger = logging.getLogger(__name__)


def initializer_node(state: SwarmState) -> SwarmState:
    """
    Normalise input deals into DealScores entries.

    Expects `state["deals"]` to already contain DealScores dicts populated
    by the pipeline's entry point, or raw dicts that need deal_id injection.
    Ensures every deal has an empty `dimensions` dict and null composite fields.
    """
    normalised: List[DealScores] = []
    for deal in state["deals"]:
        deal_id = deal.get("deal_id") or str(uuid.uuid4())
        deal_data = deal.get("deal_data") or {k: v for k, v in deal.items() if k != "deal_id"}
        normalised.append(
            DealScores(
                deal_id=deal_id,
                deal_data=deal_data,
                dimensions={},
                composite_score=None,
                rank=None,
                rank_explanation=None,
            )
        )
    logger.info("Initializer: normalised %d deals", len(normalised))
    state["deals"] = normalised
    return state
