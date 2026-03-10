"""
Strategist agent. Proposes experiments grounded in research corpus.
Uses analysis model (qwen3.5-397b).
"""
import json
import uuid
from pathlib import Path
from src.shared.llm_client import chat_analysis
from src.shared.config import SharedConfig
from src.swarm.state import SwarmState
from src.swarm.bandit import allocate
from src.swarm.memory.qdrant_store import find_similar

cfg = SharedConfig()

SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "strategist_system.md"
USER_PROMPT = Path(__file__).parent.parent / "prompts" / "strategist_user.md"


def run_strategist(state: SwarmState) -> dict:
    """Run the Strategist agent. Returns experiment specs and allocation."""
    # Compute allocation via Thompson Sampling
    allocation = allocate(
        bandit_state=state.bandit_state,
        batch_size=cfg.SWARM_BATCH_SIZE,
        exploration_pct=cfg.EXPLORATION_BUDGET_PCT,
    )

    # Get similar past experiments to avoid repetition
    similar = []
    if state.experiment_results:
        for result in state.experiment_results[-10:]:
            hits = find_similar(result, limit=3)
            similar.extend(hits)

    # Build prompt
    system = SYSTEM_PROMPT.read_text() if SYSTEM_PROMPT.exists() else "You are the Strategist agent."
    user_template = USER_PROMPT.read_text() if USER_PROMPT.exists() else "{allocation_json}"

    user = user_template.format(
        batch_size=cfg.SWARM_BATCH_SIZE,
        available_pairs_json=json.dumps(state.available_pairs, indent=2),
        champion_metrics_json=json.dumps(state.champion_metrics, indent=2),
        allocation_json=json.dumps(allocation, indent=2),
        insights_list="\n".join(f"- {i}" for i in state.active_insights),
        similar_experiments_json=json.dumps(similar[:20], indent=2, default=str),
        relevant_research_json=json.dumps(state.relevant_research[:30], indent=2, default=str),
        feature_cols_list="return_1, return_5, return_10, return_21, sma_5, sma_10, sma_21, sma_50, "
                         "ema_5, ema_10, ema_21, ema_50, volatility_10, volatility_21, rsi_14, "
                         "macd, macd_signal, macd_histogram, bb_upper, bb_lower, bb_width, "
                         "atr_14, volume_sma_10, volume_ratio, price_vs_sma50",
    )

    response = chat_analysis(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    try:
        clean = response.strip().removeprefix("```json").removesuffix("```").strip()
        specs = json.loads(clean)
        if isinstance(specs, dict) and "experiments" in specs:
            specs = specs["experiments"]
        if not isinstance(specs, list):
            specs = [specs]
    except json.JSONDecodeError:
        specs = []

    # Ensure each spec has an experiment_id
    for spec in specs:
        if "experiment_id" not in spec:
            spec["experiment_id"] = str(uuid.uuid4())

    return {
        "experiment_specs": specs,
        "allocation": allocation,
        "similar_past_experiments": similar[:20],
    }
