"""
State definitions for the Tokyo VC Deal Scoring Swarm.

All TypedDicts used across LangGraph nodes are defined here.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class DimensionScore(TypedDict):
    """Score produced by a single dimension-scoring agent."""

    score: float       # 0–10
    weight: float      # importance in composite (from config, overridable)
    rationale: str     # 2-sentence explanation


class DealScores(TypedDict):
    """Per-deal state: raw deal data plus all dimension scores."""

    deal_id: str
    deal_data: Dict                           # original input JSON
    dimensions: Dict[str, DimensionScore]    # keyed by dimension name
    composite_score: Optional[float]         # filled by ranker node
    rank: Optional[int]                      # filled by ranker node
    rank_explanation: Optional[str]          # filled by formatter node


class SwarmState(TypedDict):
    """Top-level LangGraph state shared across all nodes."""

    deals: List[DealScores]
    global_config: Dict[str, float]   # dimension_name → weight (overrides config.yaml)
    ranked_output: Optional[List[RankedDeal]]
    error: Optional[str]


class RankedDeal(TypedDict):
    """Output schema for a single ranked deal."""

    rank: int
    deal_id: str
    composite_score: float
    dimensions: Dict[str, DimensionScore]
    explanation: str
