"""Pydantic schemas for I/O validation.

Input/output schemas for the economic calendar agent API and tool interfaces.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ImpactLevel(str, Enum):
    """Impact classification for economic events."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NONE = "None"


class SurpriseDirection(str, Enum):
    """Direction of actual vs forecast surprise."""

    LARGE_POSITIVE = "large_positive"
    POSITIVE = "positive"
    INLINE = "inline"
    NEGATIVE = "negative"
    LARGE_NEGATIVE = "large_negative"


class EconomicCalendarInput(BaseModel):
    """Input schema for economic calendar tool."""

    pairs: list[str] = Field(
        default=["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"],
        description="FX pairs to analyze",
    )
    hours_ahead: int = Field(
        default=48,
        ge=1,
        le=168,
        description="How many hours ahead to look",
    )
    min_impact: ImpactLevel = Field(
        default=ImpactLevel.MEDIUM,
        description="Minimum impact level to include",
    )
    include_historical: bool = Field(
        default=True,
        description="Include recent releases with surprise analysis",
    )


class EconomicEventOutput(BaseModel):
    """Output schema for a single economic event."""

    event_id: str = Field(description="Unique event identifier")
    event_name: str = Field(description="Event name (e.g., 'Non-Farm Payrolls')")
    event_type: str = Field(description="Canonical event type for scoring")
    country: str = Field(description="Country code (e.g., 'US', 'EU')")
    currency: str = Field(description="Currency code (e.g., 'USD', 'EUR')")
    event_datetime: datetime = Field(description="Event release time (UTC)")
    impact: ImpactLevel = Field(description="Expected impact level")

    # Data values
    actual: Optional[float] = Field(None, description="Actual value (if released)")
    estimate: Optional[float] = Field(None, description="Consensus forecast")
    previous: Optional[float] = Field(None, description="Previous period value")

    # Correlation scores
    relevance_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Relevance score per pair (0.0-1.0)",
    )
    surprise_zscore: Optional[float] = Field(
        None,
        description="Standardized surprise z-score",
    )
    surprise_direction: Optional[SurpriseDirection] = Field(
        None,
        description="Surprise classification",
    )
    time_decay_factor: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Time decay multiplier (0.0-1.0)",
    )

    # Composite scores per pair
    composite_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Final composite score per pair",
    )

    # Historical context
    avg_pip_movement: Optional[dict[str, float]] = Field(
        None,
        description="Historical average pip movement per pair",
    )
    similar_scenarios: Optional[list[str]] = Field(
        None,
        description="IDs of similar historical events",
    )


class MacroRiskLevel(str, Enum):
    """Aggregate macro risk assessment."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EconomicContext(BaseModel):
    """Complete economic context for trading decisions."""

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Analysis timestamp",
    )
    events: list[EconomicEventOutput] = Field(
        default_factory=list,
        description="Scored economic events",
    )
    macro_risk: dict[str, MacroRiskLevel] = Field(
        default_factory=dict,
        description="Risk level per pair",
    )
    high_impact_imminent: list[EconomicEventOutput] = Field(
        default_factory=list,
        description="Events within 30 minutes",
    )
    summary: str = Field(
        default="",
        description="Human-readable summary for LLM reasoning",
    )
    raw_data_summary: str = Field(
        default="",
        description="Raw scored event listing (preserved for JSON consumers)",
    )
