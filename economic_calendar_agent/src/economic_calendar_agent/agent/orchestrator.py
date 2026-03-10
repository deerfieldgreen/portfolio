"""LLM orchestrator node for routing and decision-making.

Uses an LLM to analyze gathered context and decide which tool to call next,
or whether enough information has been collected to make a trading decision.
"""
from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_settings
from .state import FXTradingState

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an FX trading analysis assistant. Your role is to:

1. Analyze the current state of available market data
2. Determine if more data is needed before making a recommendation
3. Route to appropriate tool nodes to gather missing data
4. Provide trading insights when sufficient data is available

Available tools:
- economic_calendar: Get upcoming/recent economic events with correlation analysis
- technical_analysis: Analyze price action and technical indicators (stub)
- sentiment_analysis: Assess market sentiment from news/social (stub)
- risk_check: Evaluate position sizing and risk parameters (stub)
- execute: Execute a trading decision (stub)

Decision process:
1. If economic_context is missing → route to economic_calendar
2. If you need technical confirmation → route to technical_analysis
3. If you need sentiment check → route to sentiment_analysis
4. If you need risk assessment → route to risk_check
5. If you have enough data → route to execute OR provide recommendation
6. Always prioritize economic_calendar as the primary data source

Respond with your analysis and the next tool to call, or END if complete."""


async def orchestrator_node(state: FXTradingState) -> dict:
    """LLM-based orchestrator for tool routing.

    Args:
        state: Current agent state

    Returns:
        Dict with next_action and optionally new messages
    """
    settings = get_settings()

    # Initialize LLM (Novita — OpenAI-compatible endpoint)
    llm = ChatOpenAI(
        model=settings.novita_llm_model,
        temperature=settings.novita_llm_temperature,
        max_tokens=settings.novita_llm_max_tokens,
        api_key=settings.novita_api_key.get_secret_value(),
        base_url=settings.novita_base_url,
    )

    # Build context message
    context_parts = []

    if state.get("economic_context"):
        context_parts.append(
            f"Economic Context: {len(state['economic_context'].events)} events analyzed"
        )
        context_parts.append(
            f"High Impact Imminent: {len(state['economic_context'].high_impact_imminent)}"
        )
        context_parts.append(f"Macro Risk: {state['economic_context'].macro_risk}")

    if state.get("technical_signals"):
        context_parts.append("Technical signals: Available")

    if state.get("sentiment_scores"):
        context_parts.append("Sentiment scores: Available")

    if state.get("risk_assessment"):
        context_parts.append("Risk assessment: Available")

    context_str = "\n".join(context_parts) if context_parts else "No data gathered yet"

    # Create prompt
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"""Current state:
{context_str}

Target pairs: {state.get('target_pairs', [])}
Current positions: {len(state.get('current_positions', []))}

What should we do next? Respond with one of:
- economic_calendar
- technical_analysis
- sentiment_analysis
- risk_check
- execute
- END (if analysis complete)"""
        ),
    ]

    try:
        logger.info("Orchestrator calling LLM for routing decision")

        response = await llm.ainvoke(messages)
        content = response.content.strip().lower()

        # Parse next action from response
        next_action = _parse_next_action(content)

        logger.info(
            "Orchestrator decision",
            extra={"next_action": next_action, "llm_response": content},
        )

        return {
            "next_action": next_action,
            "messages": [AIMessage(content=response.content)],
        }

    except Exception as e:
        logger.error(
            "Orchestrator node failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        return {"error": f"Orchestrator error: {str(e)}", "next_action": "END"}


def _parse_next_action(
    llm_response: str,
) -> Literal[
    "economic_calendar",
    "technical_analysis",
    "sentiment_analysis",
    "risk_check",
    "execute",
    "END",
]:
    """Parse next action from LLM response.

    Args:
        llm_response: LLM response text

    Returns:
        Next action to take
    """
    response_lower = llm_response.lower()

    if "economic" in response_lower or "calendar" in response_lower:
        return "economic_calendar"
    elif "technical" in response_lower:
        return "technical_analysis"
    elif "sentiment" in response_lower:
        return "sentiment_analysis"
    elif "risk" in response_lower:
        return "risk_check"
    elif "execute" in response_lower:
        return "execute"
    elif "end" in response_lower or "complete" in response_lower:
        return "END"
    else:
        # Default: if no context, gather economic data
        return "economic_calendar"


def route_by_context(state: FXTradingState) -> str:
    """Conditional edge function for routing based on next_action.

    Falls back to deterministic routing when the LLM-parsed action
    would re-visit a node that already populated its state field.

    Args:
        state: Current agent state

    Returns:
        Name of next node to execute
    """
    next_action = state.get("next_action", "economic_calendar")

    # Guard: if economic_context is already populated and LLM still
    # routes to economic_calendar, override to END.
    if next_action == "economic_calendar" and state.get("economic_context") is not None:
        logger.info("Economic context already gathered — routing to END")
        return "END"

    logger.info("Routing to node", extra={"next_action": next_action})

    return next_action
