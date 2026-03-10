"""
Meta-Learner agent. Analyzes results, extracts insights, updates bandit.
Uses analysis model (qwen3.5-397b).
"""
import json
from pathlib import Path
from src.shared.llm_client import chat_analysis
from src.swarm.state import SwarmState
from src.swarm.bandit import update_bandit
from src.swarm.memory.qdrant_store import upsert_experiment
from src.swarm.memory.insight_store import store_insight
from src.swarm.memory.clickhouse_analytics import log_experiment

SYSTEM_PROMPT = Path(__file__).parent.parent / "prompts" / "meta_learner_system.md"


def run_meta_learner(state: SwarmState) -> dict:
    """Analyze results, extract insights, update bandit state."""
    bandit_state = dict(state.bandit_state)

    # 1. Store experiments in Qdrant + ClickHouse
    for i, result in enumerate(state.experiment_results):
        spec = state.experiment_specs[i] if i < len(state.experiment_specs) else {}

        # Store in Qdrant
        try:
            novelty = upsert_experiment(
                experiment_id=result.get("experiment_id", ""),
                spec=spec,
                result=result,
            )
            result["novelty_score"] = novelty
        except Exception:
            pass

        # Log to ClickHouse
        try:
            log_experiment({
                "run_id": result.get("run_id", ""),
                "experiment_id": result.get("experiment_id", ""),
                "architecture": spec.get("architecture", ""),
                "strategy_type": spec.get("strategy_type", ""),
                "pair": spec.get("pair", ""),
                "timeframe": spec.get("timeframe", ""),
                "status": result.get("status", "unknown"),
                "metrics": result.get("metrics", {}),
                "swarm_cycle": state.cycle_number,
                "research_direction": spec.get("research_direction", ""),
                "bandit_arm": spec.get("research_direction", ""),
            })
        except Exception:
            pass

        # Update bandit
        arm = spec.get("research_direction", "")
        reward = 1.0 if result.get("improved", False) else 0.0
        bandit_state = update_bandit(bandit_state, arm, reward)

    # 2. Extract insights via LLM
    system = SYSTEM_PROMPT.read_text() if SYSTEM_PROMPT.exists() else "You are the Meta-Learner."

    context = {
        "cycle": state.cycle_number,
        "results": state.experiment_results,
        "specs": state.experiment_specs,
        "current_insights": state.active_insights,
    }

    response = chat_analysis(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, indent=2, default=str)},
        ],
        temperature=0.5,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(response.strip().removeprefix("```json").removesuffix("```").strip())
        new_insights = parsed.get("insights", [])
    except json.JSONDecodeError:
        new_insights = []

    # Store new insights
    for insight in new_insights:
        try:
            store_insight(
                text=insight.get("text", ""),
                source_run_ids=[r.get("run_id", "") for r in state.experiment_results],
                category=insight.get("category", "general"),
                confidence=insight.get("confidence", 0.5),
            )
        except Exception:
            pass

    return {
        "bandit_state": bandit_state,
    }
