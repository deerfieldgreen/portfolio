"""Composite ranker node: computes weighted scores and sorts deals."""

from __future__ import annotations

import logging

from ..config import Config
from ..state import SwarmState

logger = logging.getLogger(__name__)


def composite_ranker_node(state: SwarmState) -> SwarmState:
    """
    Compute weighted composite score for each deal and sort descending.

    Inverted dimensions (e.g. risk_regulatory) have their score transformed
    as (10 - score) before weighting, as specified in config.yaml.
    """
    inverted = Config.get_inverted_dimensions()

    for deal in state["deals"]:
        dims = deal["dimensions"]
        if not dims:
            deal["composite_score"] = 0.0
            continue

        numerator = 0.0
        denominator = 0.0
        for dim_name, dim_score in dims.items():
            raw = float(dim_score["score"])
            effective = (10.0 - raw) if dim_name in inverted else raw
            w = float(dim_score["weight"])
            numerator += effective * w
            denominator += w

        deal["composite_score"] = round(numerator / denominator, 4) if denominator else 0.0

    state["deals"].sort(key=lambda d: d["composite_score"] or 0.0, reverse=True)

    for rank, deal in enumerate(state["deals"], start=1):
        deal["rank"] = rank

    logger.info("Ranker: ranked %d deals", len(state["deals"]))
    return state
