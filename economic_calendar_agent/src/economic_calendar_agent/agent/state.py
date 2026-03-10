"""LangGraph state definition for FX trading agent.

TypedDict defining the complete state passed between graph nodes.
"""
from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from ..models.schemas import EconomicContext


class TechnicalSignals(TypedDict, total=False):
    """Technical analysis signals (stub for Phase 2)."""

    symbol: str
    trend: str
    support: Optional[float]
    resistance: Optional[float]
    indicators: dict[str, float]


class SentimentScores(TypedDict, total=False):
    """Market sentiment scores (stub for Phase 2)."""

    overall: float
    news: float
    social: float
    sources: list[str]


class RiskAssessment(TypedDict, total=False):
    """Risk assessment results (stub for Phase 2)."""

    risk_level: str
    position_size: float
    stop_loss: Optional[float]
    take_profit: Optional[float]


class Position(TypedDict, total=False):
    """Current trading position."""

    pair: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    current_pnl: float


class FXTradingState(TypedDict):
    """Complete agent state for FX trading decisions.

    This state is passed between all nodes in the graph. Each node
    can read any field and update specific fields it owns.
    """

    # Messages for conversation tracking
    messages: Annotated[list[BaseMessage], add_messages]

    # Tool outputs (each owned by one tool node)
    economic_context: Optional[EconomicContext]
    technical_signals: Optional[TechnicalSignals]
    sentiment_scores: Optional[SentimentScores]
    risk_assessment: Optional[RiskAssessment]

    # Input parameters
    target_pairs: list[str]
    current_positions: list[Position]

    # Control flow
    next_action: Optional[str]  # Which node to route to next
    error: Optional[str]  # Error message if any node fails
