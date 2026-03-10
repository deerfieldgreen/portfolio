"""Domain models for economic events.

Internal representations used by the correlation and scoring modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .schemas import ImpactLevel, SurpriseDirection


@dataclass
class EconomicEvent:
    """Core economic event model."""

    event_id: str
    event_name: str
    event_type: str  # Canonical type for scoring (e.g., "NFP", "CPI", "FOMC")
    country: str
    currency: str
    event_datetime: datetime
    impact: ImpactLevel

    actual: Optional[float] = None
    estimate: Optional[float] = None
    previous: Optional[float] = None

    # Metadata
    unit: Optional[str] = None  # e.g., "%", "K", "Index"
    source: str = "FMP"  # Data source


@dataclass
class DecayParams:
    """Time decay parameters for an event type."""

    event_type: str
    fast_halflife_minutes: float  # Fast component half-life
    slow_halflife_minutes: float  # Slow component half-life
    alpha: float  # Weight of fast component (0.0-1.0)

    def __post_init__(self):
        """Validate decay parameters."""
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError(f"alpha must be in [0, 1], got {self.alpha}")
        if self.fast_halflife_minutes <= 0:
            raise ValueError(f"fast_halflife_minutes must be > 0, got {self.fast_halflife_minutes}")
        if self.slow_halflife_minutes <= 0:
            raise ValueError(f"slow_halflife_minutes must be > 0, got {self.slow_halflife_minutes}")


@dataclass
class ScoredEvent:
    """Economic event with computed correlation scores."""

    event: EconomicEvent
    relevance_scores: dict[str, float] = field(default_factory=dict)  # pair -> score
    surprise_zscore: Optional[float] = None
    surprise_direction: Optional[SurpriseDirection] = None
    time_decay_factor: float = 1.0
    composite_scores: dict[str, float] = field(default_factory=dict)  # pair -> final score
    minutes_since_release: Optional[float] = None

    def get_score(self, pair: str) -> float:
        """Get composite score for a specific pair."""
        return self.composite_scores.get(pair, 0.0)

    def is_high_impact(self, threshold: float = 0.7) -> bool:
        """Check if any pair has a high composite score."""
        return any(score >= threshold for score in self.composite_scores.values())


@dataclass
class PipStats:
    """Historical pip movement statistics for an event type."""

    event_type: str
    pair: str
    impact: ImpactLevel
    avg_pip_movement_15m: float
    avg_pip_movement_1h: float
    sample_count: int
    std_dev: float
