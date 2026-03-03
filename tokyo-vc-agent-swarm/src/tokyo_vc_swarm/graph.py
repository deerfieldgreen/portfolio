"""
LangGraph StateGraph wiring for the Tokyo VC Deal Scoring Swarm.

Graph topology (linear):
    START → initializer → scoring_orchestrator → composite_ranker → output_formatter → END
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from .nodes import (
    composite_ranker_node,
    initializer_node,
    output_formatter_node,
    scoring_orchestrator_node,
)
from .state import SwarmState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build and compile the deal scoring swarm graph."""
    logger.info("Building Tokyo VC scoring swarm graph")

    builder = StateGraph(SwarmState)

    builder.add_node("initializer", initializer_node)
    builder.add_node("scoring_orchestrator", scoring_orchestrator_node)
    builder.add_node("composite_ranker", composite_ranker_node)
    builder.add_node("output_formatter", output_formatter_node)

    builder.add_edge(START, "initializer")
    builder.add_edge("initializer", "scoring_orchestrator")
    builder.add_edge("scoring_orchestrator", "composite_ranker")
    builder.add_edge("composite_ranker", "output_formatter")
    builder.add_edge("output_formatter", END)

    graph = builder.compile()
    logger.info("Tokyo VC scoring swarm graph compiled")
    return graph
