"""Log model + metrics to MLflow."""
import os
import json
import pickle
import tempfile
from typing import Dict, Any, Optional

import mlflow
from src.shared.config import SharedConfig

cfg = SharedConfig()


def log_experiment(
    pair: str,
    timeframe: str,
    architecture: str,
    model,
    scaler,
    metrics: Dict[str, float],
    config: Dict[str, Any],
    feature_cols: list,
    model_type: str = "pytorch",
) -> str:
    """
    Log a complete experiment to MLflow.
    Returns run_id.
    """
    registry_name = f"fx-{pair}-{timeframe}"

    mlflow.set_experiment(cfg.MLFLOW_EXPERIMENT_NAME)

    with mlflow.start_run() as run:
        # Log params
        mlflow.log_param("pair", pair)
        mlflow.log_param("timeframe", timeframe)
        mlflow.log_param("architecture", architecture)
        mlflow.log_param("model_type", model_type)
        mlflow.set_tag("architecture", architecture)

        for k, v in config.items():
            if isinstance(v, (str, int, float, bool)):
                mlflow.log_param(k, v)

        # Log metrics
        for k, v in metrics.items():
            mlflow.log_metric(k, v)

        # Save artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            # Config
            config_path = os.path.join(tmpdir, "config.json")
            config["feature_cols"] = feature_cols
            with open(config_path, "w") as f:
                json.dump(config, f)

            # Scaler
            scaler_path = os.path.join(tmpdir, "scaler.pkl")
            with open(scaler_path, "wb") as f:
                pickle.dump(scaler, f)

            # Model
            if model_type == "pytorch":
                import torch
                model_path = os.path.join(tmpdir, "model.pt")
                torch.save(model, model_path)
                artifacts = {
                    "config": config_path,
                    "scaler": scaler_path,
                    "model_pt": model_path,
                }
            else:
                model_path = os.path.join(tmpdir, "model.pkl")
                with open(model_path, "wb") as f:
                    pickle.dump(model, f)
                artifacts = {
                    "config": config_path,
                    "scaler": scaler_path,
                    "model_pkl": model_path,
                }

            # Log as pyfunc
            from src.training.pyfunc_wrapper import FXPredictionModel
            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=FXPredictionModel(),
                artifacts=artifacts,
                registered_model_name=registry_name,
            )

        # Write run_id for Argo parameter passing
        with open("/tmp/run_id", "w") as f:
            f.write(run.info.run_id)

        return run.info.run_id
