"""LLM synthesis node for economic calendar analysis.

Takes the raw scored event data and produces a narrative analysis
with directional bias, risk windows, and trading implications.
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ...config import get_settings
from ..state import FXTradingState

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = """\
You are an FX macro analyst. You will receive scored economic calendar data \
for specific currency pairs. Produce a concise trading-oriented analysis.

Structure your response as:

## Key Events (top 3-5 by composite score)
For each: event name, country, time, impact, and why it matters for the pair(s).

## Risk Windows
Identify clusters of high-impact events that create elevated volatility windows. \
Include specific time ranges.

## Directional Bias
For each requested pair, state any directional bias implied by the economic data \
(bullish/bearish/neutral on the base currency) with brief reasoning.

## Trading Implications
Actionable takeaways: position sizing considerations, times to avoid trading, \
potential breakout catalysts.

Be specific and quantitative where possible. Reference composite scores. \
Do not repeat raw data — synthesize it into insight."""


async def synthesis_node(state: FXTradingState) -> dict:
    """Synthesize scored economic data into narrative analysis.

    Reads raw_data_summary from economic_context and overwrites
    summary with the LLM-generated narrative.

    Args:
        state: Current agent state with populated economic_context

    Returns:
        Dict with updated economic_context
    """
    economic_context = state.get("economic_context")
    if economic_context is None:
        logger.warning("Synthesis node called without economic_context")
        return {}

    raw_summary = economic_context.raw_data_summary or economic_context.summary
    if not raw_summary:
        logger.info("No data to synthesize")
        return {}

    settings = get_settings()
    pairs = state.get("target_pairs", settings.target_pairs)

    try:
        llm = ChatOpenAI(
            model=settings.novita_llm_model,
            temperature=settings.novita_llm_temperature,
            max_tokens=settings.novita_llm_max_tokens,
            api_key=settings.novita_api_key.get_secret_value(),
            base_url=settings.novita_base_url,
        )

        messages = [
            SystemMessage(content=_SYNTHESIS_PROMPT),
            HumanMessage(
                content=(
                    f"Target pairs: {', '.join(pairs)}\n\n"
                    f"{raw_summary}"
                )
            ),
        ]

        logger.info("Synthesis node calling LLM")
        response = await llm.ainvoke(messages)
        narrative = response.content.strip()

        # Overwrite summary with narrative; raw_data_summary is preserved
        economic_context.summary = narrative

        logger.info(
            "Synthesis node complete",
            extra={"narrative_length": len(narrative)},
        )

        return {"economic_context": economic_context}

    except Exception as e:
        logger.error(
            "Synthesis node failed — keeping raw summary",
            extra={"error": str(e)},
            exc_info=True,
        )
        # On failure, leave summary unchanged (raw data still useful)
        return {}
