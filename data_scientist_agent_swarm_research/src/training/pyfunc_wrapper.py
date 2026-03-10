"""
MLflow pyfunc wrapper for serving models.
Wraps any PyTorch/sklearn/XGBoost model into a standard interface.
"""
import os
import numpy as np
import pandas as pd
import mlflow.pyfunc


class FXPredictionModel(mlflow.pyfunc.PythonModel):
    """
    Generic pyfunc wrapper. Loads model + scaler + config from artifacts.
    predict() takes a DataFrame of features and returns predicted close prices.
    """

    def load_context(self, context):
        import pickle
        import torch

        artifacts = context.artifacts
        self.config = {}

        # Load config
        if "config" in artifacts:
            with open(artifacts["config"], "r") as f:
                import json
                self.config = json.load(f)

        # Load scaler
        if "scaler" in artifacts:
            with open(artifacts["scaler"], "rb") as f:
                self.scaler = pickle.load(f)
        else:
            self.scaler = None

        # Load model (PyTorch or pickle)
        if "model_pt" in artifacts:
            self.model = torch.load(artifacts["model_pt"], map_location="cpu")
            self.model.eval()
            self.model_type = "pytorch"
        elif "model_pkl" in artifacts:
            with open(artifacts["model_pkl"], "rb") as f:
                self.model = pickle.load(f)
            self.model_type = "sklearn"
        else:
            raise ValueError("No model artifact found")

    def predict(self, context, model_input: pd.DataFrame) -> np.ndarray:
        import torch

        feature_cols = self.config.get("feature_cols", model_input.columns.tolist())
        X = model_input[feature_cols].values

        # Scale if scaler exists (ONLY transform, never fit)
        if self.scaler is not None:
            X = self.scaler.transform(X)

        if self.model_type == "pytorch":
            seq_len = self.config.get("sequence_length", 60)
            # Create sequences from the last seq_len rows
            if len(X) >= seq_len:
                X_seq = X[-seq_len:].reshape(1, seq_len, -1)
                X_tensor = torch.FloatTensor(X_seq)
                with torch.no_grad():
                    pred = self.model(X_tensor).numpy().flatten()
            else:
                pred = np.full(1, np.nan)
        else:
            pred = self.model.predict(X)

        return pred
