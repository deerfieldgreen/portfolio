"""Load champion MLflow pyfunc model and run inference."""
import os
from typing import Optional

import mlflow
import pandas as pd


def predict(features_df: pd.DataFrame, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
    """
    Load champion model for this pair/TF and predict next close.
    Returns DataFrame with predictions or None if no champion exists.
    """
    registry = f"fx-{pair}-{timeframe}"
    model_uri = f"models:/{registry}/champion"

    try:
        model = mlflow.pyfunc.load_model(model_uri)
    except Exception:
        return None

    # Get model metadata for architecture tag
    client = mlflow.tracking.MlflowClient()
    version_info = client.get_model_version_by_alias(registry, "champion")
    run = client.get_run(version_info.run_id)
    architecture = run.data.tags.get("architecture", "unknown")

    # Predict
    preds = model.predict(features_df)

    result = pd.DataFrame({
        "timestamp": features_df.index,
        "pred_next_close": preds,
        "model_registry": registry,
        "model_version": version_info.version,
        "architecture": architecture,
    })

    return result
