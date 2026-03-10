"""Sentiment analysis tool node (stub for Phase 2)."""
from __future__ import annotations

import logging

from ..state import FXTradingState, SentimentScores

logger = logging.getLogger(__name__)


async def sentiment_analysis_node(state: FXTradingState) -> dict:
    """Analyze market sentiment (stub).

    Args:
        state: Current agent state

    Returns:
        Dict with sentiment_scores field populated
    """
    logger.info("Sentiment analysis node (stub)")

    # Stub implementation — return neutral sentiment
    sentiment_scores = SentimentScores(
        overall=0.5,
        news=0.5,
        social=0.5,
        sources=["stub"],
    )

    return {"sentiment_scores": sentiment_scores}
