"""Scoring orchestrator node: fans out to all 7 dimension agents via asyncio.gather."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from ..agents import ALL_AGENT_CLASSES, BaseScoringAgent
from ..config import Config
from ..state import DealScores, SwarmState

logger = logging.getLogger(__name__)

_MOCK_SCORES: Dict[str, float] = {
    "market": 7.5,
    "team": 8.0,
    "product": 6.5,
    "traction": 7.0,
    "syndication_fit": 8.5,
    "risk_regulatory": 6.0,
    "japan_fit": 7.0,
}


def _build_agents(weight_overrides: Dict[str, float]) -> List[BaseScoringAgent]:
    default_weights = Config.get_default_weights()
    agents = []
    for cls in ALL_AGENT_CLASSES:
        dim = cls.DIMENSION_NAME
        weight = weight_overrides.get(dim, default_weights.get(dim, 1.0))
        agents.append(cls(weight=weight))
    return agents


async def _score_deal_async(
    deal: DealScores,
    agents: List[BaseScoringAgent],
    mock: bool,
) -> DealScores:
    """Run all agents concurrently for a single deal."""
    if mock:
        for agent in agents:
            dim = agent.DIMENSION_NAME
            deal["dimensions"][dim] = {
                "score": _MOCK_SCORES.get(dim, 5.0),
                "weight": agent.weight,
                "rationale": f"[MOCK] Placeholder rationale for {dim}.",
            }
        return deal

    tasks = [agent.score_deal(deal["deal_data"]) for agent in agents]
    results = await asyncio.gather(*tasks)
    for agent, dim_score in zip(agents, results):
        deal["dimensions"][agent.DIMENSION_NAME] = dim_score
    return deal


def scoring_orchestrator_node(state: SwarmState) -> SwarmState:
    """
    Score all deals across all 7 dimensions in parallel.

    Uses asyncio.gather to fire all dimension LLM calls concurrently,
    then collects results back into state["deals"].
    """
    mock: bool = state.get("global_config", {}).get("_mock", False)  # type: ignore[arg-type]
    weight_overrides = {
        k: v for k, v in state.get("global_config", {}).items() if not k.startswith("_")
    }
    agents = _build_agents(weight_overrides)

    async def _score_all() -> List[DealScores]:
        return await asyncio.gather(
            *[_score_deal_async(deal, agents, mock) for deal in state["deals"]]
        )

    scored = asyncio.run(_score_all())
    state["deals"] = scored
    logger.info("Scorer: scored %d deals across %d dimensions", len(scored), len(agents))
    return state
