"""MLflow alias helpers using REST API."""
import os
import requests
from typing import Dict, List, Optional

import mlflow


def _tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")


def set_alias(registry_name: str, alias: str, version: str) -> bool:
    """Set an MLflow model alias via REST API."""
    url = f"{_tracking_uri()}/api/2.0/mlflow/registered-models/set-alias"
    resp = requests.post(url, json={
        "name": registry_name,
        "alias": alias,
        "version": version,
    })
    return resp.status_code == 200


def get_model_version_by_alias(registry_name: str, alias: str) -> Optional[str]:
    """Get model version number by alias."""
    url = f"{_tracking_uri()}/api/2.0/mlflow/registered-models/get-model-version-by-alias"
    resp = requests.get(url, params={"name": registry_name, "alias": alias})
    if resp.status_code == 200:
        return resp.json().get("model_version", {}).get("version")
    return None


def get_all_champion_metrics(available_pairs: List[Dict]) -> Dict[str, Dict[str, float]]:
    """
    Get champion model metrics for all active pair/TF combos.
    Returns: {"fx-USD_JPY-H1": {"sharpe": 1.2, ...}, ...}
    """
    champions = {}
    for item in available_pairs:
        registry = f"fx-{item['pair']}-{item['timeframe']}"
        version = get_model_version_by_alias(registry, "champion")
        if version:
            try:
                client = mlflow.tracking.MlflowClient()
                run = client.get_model_version(registry, version)
                run_data = client.get_run(run.run_id)
                champions[registry] = dict(run_data.data.metrics)
            except Exception:
                pass
    return champions


def promote_candidate(registry_name: str, version: str) -> bool:
    """
    Promote a candidate model:
    1. Move current champion → previous-champion
    2. Move candidate → champion
    """
    current_champion = get_model_version_by_alias(registry_name, "champion")
    if current_champion:
        set_alias(registry_name, "previous-champion", current_champion)
    return set_alias(registry_name, "champion", version)
