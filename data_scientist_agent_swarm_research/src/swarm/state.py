# src/swarm/state.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

class SwarmPhase(str, Enum):
    PLANNING = "planning"
    DESIGN = "design"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    LEARNING = "learning"
    CIRCUIT_BREAK = "circuit_break"

@dataclass
class ExperimentSpec:
    """Strategist output. Architecture-agnostic — any model type."""
    experiment_id: str
    research_direction: str
    architecture: str
    model_family: str
    feature_set: List[str]
    strategy_type: str
    strategy_description: str
    pair: str
    timeframe: str
    hyperparameter_hints: Dict[str, Any]
    reasoning: str
    research_references: List[str]
    predicted_sharpe: Optional[float] = None

@dataclass
class ExperimentResult:
    experiment_id: str
    run_id: str
    status: str
    metrics: Dict[str, float]
    deflated_sharpe: Optional[float] = None
    pbo: Optional[float] = None
    failure_detail: Optional[str] = None
    training_time_sec: float = 0.0
    estimated_cost_usd: float = 0.0

@dataclass
class SwarmState:
    phase: SwarmPhase = SwarmPhase.PLANNING
    cycle_number: int = 0
    bandit_state: Dict[str, Any] = field(default_factory=dict)
    allocation: Dict[str, int] = field(default_factory=dict)
    experiment_specs: List[Dict] = field(default_factory=list)
    experiment_results: List[Dict] = field(default_factory=list)
    generated_code: Dict[str, str] = field(default_factory=dict)
    active_insights: List[str] = field(default_factory=list)
    similar_past_experiments: List[Dict] = field(default_factory=list)
    champion_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    available_pairs: List[Dict] = field(default_factory=list)
    relevant_research: List[Dict] = field(default_factory=list)
    crawl_summary: Dict[str, int] = field(default_factory=dict)
    consecutive_no_improvement: int = 0
    errors: List[str] = field(default_factory=list)
