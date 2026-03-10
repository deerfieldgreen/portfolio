"""Main entry point for economic calendar agent.

CLI interface for running the LangGraph agent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .agent.graph import build_graph
from .agent.state import FXTradingState
from .config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def run_agent(pairs: list[str]) -> dict:
    """Run the economic calendar agent.

    Args:
        pairs: FX pairs to analyze

    Returns:
        Final agent state
    """
    logger.info("Starting economic calendar agent", extra={"pairs": pairs})

    # Build graph
    graph = build_graph()

    # Initial state
    initial_state: FXTradingState = {
        "messages": [],
        "economic_context": None,
        "technical_signals": None,
        "sentiment_scores": None,
        "risk_assessment": None,
        "target_pairs": pairs,
        "current_positions": [],
        "next_action": None,
        "error": None,
    }

    try:
        # Invoke graph
        logger.info("Invoking agent graph")
        final_state = await graph.ainvoke(
            initial_state,
            config={"recursion_limit": 10},
        )

        logger.info("Agent completed successfully")
        return final_state

    except Exception as e:
        logger.error("Agent execution failed", extra={"error": str(e)}, exc_info=True)
        raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Economic Calendar Agent for FX Trading"
    )
    parser.add_argument(
        "--pairs",
        type=str,
        nargs="+",
        default=None,
        help="FX pairs to analyze (e.g., USDJPY EURUSD)",
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["json", "summary"],
        default="summary",
        help="Output format",
    )

    args = parser.parse_args()

    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Get pairs from args or settings
    pairs = args.pairs if args.pairs else settings.target_pairs

    # Run agent
    try:
        final_state = asyncio.run(run_agent(pairs))

        # Output results
        if args.output == "json":
            # Full state as JSON
            output = {
                "pairs": pairs,
                "economic_context": (
                    final_state["economic_context"].model_dump(mode="json")
                    if final_state.get("economic_context")
                    else None
                ),
                "macro_risk": (
                    final_state["economic_context"].macro_risk
                    if final_state.get("economic_context")
                    else {}
                ),
                "error": final_state.get("error"),
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable summary
            if final_state.get("error"):
                print(f"❌ Error: {final_state['error']}")
            elif final_state.get("economic_context"):
                print(final_state["economic_context"].summary)
            else:
                print("No economic context available")

        sys.exit(0 if not final_state.get("error") else 1)

    except Exception as e:
        logger.error(f"Agent failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
