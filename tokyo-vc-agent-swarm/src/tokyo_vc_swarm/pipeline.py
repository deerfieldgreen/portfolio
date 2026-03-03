"""
DealScoringPipeline: high-level entry point for the Tokyo VC scoring swarm.

Wraps the compiled LangGraph and provides run() and stream() interfaces
with optional mock mode for fast iteration/testing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Generator, List, Optional

from .config import Config
from .graph import build_graph
from .state import RankedDeal, SwarmState

logger = logging.getLogger(__name__)

# Sentinel key stored in global_config to signal mock mode to scorer node
_MOCK_KEY = "_mock"


class DealScoringPipeline:
    """
    Orchestrates deal scoring across all 7 dimensions and returns a ranked list.

    Usage::

        pipeline = DealScoringPipeline()
        ranked = pipeline.run(deals)            # blocking
        for event in pipeline.stream(deals):    # streaming status + final output
            ...
    """

    def __init__(self) -> None:
        Config.validate()
        self._graph = build_graph()
        logger.info("DealScoringPipeline initialised")

    def run(
        self,
        deals: List[Dict[str, Any]],
        weight_overrides: Optional[Dict[str, float]] = None,
        mock: bool = False,
    ) -> List[RankedDeal]:
        """
        Score and rank a batch of deals (blocking).

        Args:
            deals: List of deal dicts. Each should contain at least a unique
                   identifier under "deal_id" and relevant deal data fields.
            weight_overrides: Optional per-dimension weight overrides.
                              E.g. {"traction": 2.0} raises traction importance.
            mock: If True, skip LLM calls and use stub scores. Useful for testing.

        Returns:
            Ranked list of RankedDeal dicts, best deal first.
        """
        initial_state = self._build_initial_state(deals, weight_overrides, mock)
        final_state: SwarmState = self._graph.invoke(initial_state)
        return final_state.get("ranked_output") or []

    def stream(
        self,
        deals: List[Dict[str, Any]],
        weight_overrides: Optional[Dict[str, float]] = None,
        mock: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Score and rank deals with streaming status events.

        Yields dicts with a "type" key:
        - "status": progress update with "message" string
        - "complete": final event with "ranked_output" list

        Args:
            deals: List of deal dicts.
            weight_overrides: Optional per-dimension weight overrides.
            mock: If True, use stub scores.
        """
        yield {"type": "status", "message": f"Starting scoring for {len(deals)} deal(s)..."}

        initial_state = self._build_initial_state(deals, weight_overrides, mock)

        current_state = initial_state
        node_messages = {
            "initializer": "Normalising deal inputs...",
            "scoring_orchestrator": f"Running {'mock ' if mock else ''}scoring across 7 dimensions...",
            "composite_ranker": "Computing composite scores and ranking...",
            "output_formatter": "Formatting ranked output...",
        }

        try:
            for step in self._graph.stream(current_state):
                for node_name in step:
                    msg = node_messages.get(node_name, f"Running {node_name}...")
                    yield {"type": "status", "message": msg}
                    current_state = step[node_name]
        except Exception as exc:
            logger.error("Pipeline error during streaming: %s", exc)
            yield {"type": "error", "message": str(exc)}
            return

        ranked_output = current_state.get("ranked_output") or []
        yield {"type": "complete", "ranked_output": ranked_output}

    def _build_initial_state(
        self,
        deals: List[Dict[str, Any]],
        weight_overrides: Optional[Dict[str, float]],
        mock: bool,
    ) -> SwarmState:
        global_config: Dict[str, Any] = dict(weight_overrides or {})
        if mock:
            global_config[_MOCK_KEY] = True
        return SwarmState(
            deals=list(deals),
            global_config=global_config,
            ranked_output=None,
            error=None,
        )
