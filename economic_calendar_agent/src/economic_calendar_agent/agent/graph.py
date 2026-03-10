"""LangGraph StateGraph assembly for economic calendar agent.

Wires together orchestrator and tool nodes with conditional routing.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from .nodes.economic import economic_calendar_node
from .nodes.execution import execution_node
from .nodes.risk import risk_check_node
from .nodes.sentiment import sentiment_analysis_node
from .nodes.synthesis import synthesis_node
from .nodes.technical import technical_analysis_node
from .orchestrator import orchestrator_node, route_by_context
from .state import FXTradingState

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build and compile the economic calendar agent graph.

    Graph topology:
        START → orchestrator → [conditional routing] → tool nodes → orchestrator → ...
        Any node can route to END via orchestrator

    Returns:
        Compiled StateGraph ready for .invoke()
    """
    logger.info("Building economic calendar agent graph")

    # Create graph builder
    builder = StateGraph(FXTradingState)

    # Add nodes
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("economic_calendar", economic_calendar_node)
    builder.add_node("technical_analysis", technical_analysis_node)
    builder.add_node("sentiment_analysis", sentiment_analysis_node)
    builder.add_node("risk_check", risk_check_node)
    builder.add_node("execute", execution_node)
    builder.add_node("synthesis", synthesis_node)

    # Entry point: always start with orchestrator
    builder.add_edge(START, "orchestrator")

    # Conditional routing from orchestrator based on next_action
    builder.add_conditional_edges(
        "orchestrator",
        route_by_context,
        {
            "economic_calendar": "economic_calendar",
            "technical_analysis": "technical_analysis",
            "sentiment_analysis": "sentiment_analysis",
            "risk_check": "risk_check",
            "execute": "execute",
            "END": END,
        },
    )

    # Economic calendar passes through synthesis before returning to orchestrator
    builder.add_edge("economic_calendar", "synthesis")
    builder.add_edge("synthesis", "orchestrator")
    builder.add_edge("technical_analysis", "orchestrator")
    builder.add_edge("sentiment_analysis", "orchestrator")
    builder.add_edge("risk_check", "orchestrator")
    builder.add_edge("execute", END)

    # Compile graph
    graph = builder.compile()

    logger.info("Economic calendar agent graph compiled successfully")

    return graph
