"""
Promotion gate: compare candidate vs champion.
Deterministic, no LLM calls.
"""
import os, sys, json
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import mlflow
from src.shared.config import SharedConfig
from src.shared.mlflow_utils import promote_candidate, get_model_version_by_alias
from src.shared.discord import notify_discord

cfg = SharedConfig()


def evaluate_promotion(run_id: str, pair: str, timeframe: str) -> dict:
    """
    Evaluate whether a candidate model should be promoted.
    Returns dict with promoted: bool, reason: str
    """
    registry = f"fx-{pair}-{timeframe}"
    client = mlflow.tracking.MlflowClient()
    run = client.get_run(run_id)
    metrics = run.data.metrics

    # Gate 1: Minimum directional accuracy
    da = metrics.get("directional_accuracy", 0)
    if da < cfg.MIN_DIRECTIONAL_ACCURACY:
        return {"promoted": False, "reason": f"Directional accuracy {da:.3f} < {cfg.MIN_DIRECTIONAL_ACCURACY}"}

    # Gate 2: Maximum PBO
    pbo = metrics.get("pbo", 1.0)
    if pbo > cfg.MAX_PBO:
        return {"promoted": False, "reason": f"PBO {pbo:.3f} > {cfg.MAX_PBO}"}

    # Gate 3: Compare with champion (if exists)
    champion_version = get_model_version_by_alias(registry, "champion")
    if champion_version:
        champion_run = client.get_model_version(registry, champion_version)
        champion_data = client.get_run(champion_run.run_id)
        champion_dsr = champion_data.data.metrics.get("deflated_sharpe", 0)
        candidate_dsr = metrics.get("deflated_sharpe", 0)

        improvement = candidate_dsr - champion_dsr
        if improvement < cfg.DSR_IMPROVEMENT_THRESHOLD:
            return {
                "promoted": False,
                "reason": f"DSR improvement {improvement:.4f} < threshold {cfg.DSR_IMPROVEMENT_THRESHOLD}",
            }

    # All gates passed — promote
    # Find the model version for this run
    versions = client.search_model_versions(f"name='{registry}'")
    candidate_version = None
    for v in versions:
        if v.run_id == run_id:
            candidate_version = v.version
            break

    if candidate_version:
        success = promote_candidate(registry, candidate_version)
        if success:
            msg = f"PROMOTED: {registry} v{candidate_version} (DA={da:.3f}, DSR={metrics.get('deflated_sharpe', 0):.4f})"
            notify_discord(msg)
            return {"promoted": True, "reason": msg}

    return {"promoted": False, "reason": "Could not find model version for run"}


def main():
    pair = os.environ["PAIR"]
    timeframe = os.environ["TIMEFRAME"]
    run_id = os.environ["RUN_ID"]

    result = evaluate_promotion(run_id, pair, timeframe)
    print(json.dumps(result, indent=2))

    # Write result for Argo parameter passing
    with open("/tmp/promotion_result.json", "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
