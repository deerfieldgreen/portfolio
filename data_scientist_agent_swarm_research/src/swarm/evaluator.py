"""
Deterministic evaluator. ZERO LLM calls.
Reads results from MLflow/Argo outputs, applies promotion gate.
"""
import json
import mlflow
from src.shared.config import SharedConfig
from src.shared.mlflow_utils import get_model_version_by_alias
from src.training.scaffolding.metrics import compute_all_metrics
from src.swarm.state import SwarmState

cfg = SharedConfig()


def run_evaluation(state: SwarmState) -> dict:
    """
    Process experiment results. Determine improvements.
    Returns updated state fields.
    """
    client = mlflow.tracking.MlflowClient()
    processed_results = []
    any_improvement = False

    for result in state.experiment_results:
        exp_id = result.get("experiment_id")
        run_id = result.get("run_id")

        if not run_id or result.get("status") == "crash":
            processed_results.append(result)
            continue

        try:
            run = client.get_run(run_id)
            metrics = dict(run.data.metrics)

            # Check if this beats the champion
            spec = next(
                (s for s in state.experiment_specs if s.get("experiment_id") == exp_id),
                None,
            )
            if spec:
                registry = f"fx-{spec['pair']}-{spec['timeframe']}"
                champion_key = registry
                champion = state.champion_metrics.get(champion_key, {})
                champion_dsr = champion.get("deflated_sharpe", 0)
                candidate_dsr = metrics.get("deflated_sharpe", 0)

                if candidate_dsr > champion_dsr + cfg.DSR_IMPROVEMENT_THRESHOLD:
                    any_improvement = True
                    result["improved"] = True

            result["metrics"] = metrics
            result["status"] = "evaluated"

        except Exception as e:
            result["status"] = "eval_error"
            result["failure_detail"] = str(e)

        processed_results.append(result)

    # Update consecutive no-improvement counter
    consecutive = state.consecutive_no_improvement
    if any_improvement:
        consecutive = 0
    else:
        consecutive += len(processed_results)

    return {
        "experiment_results": processed_results,
        "consecutive_no_improvement": consecutive,
    }
