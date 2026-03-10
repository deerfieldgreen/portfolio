"""Load training data from parquet, prepare for model training."""
import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
from sklearn.preprocessing import StandardScaler


def load_parquet(path: str) -> pd.DataFrame:
    """Load parquet file with proper types."""
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    return df.sort_index()


def prepare_features(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "close",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract feature matrix and target vector.
    Caller is responsible for splitting BEFORE calling this.
    """
    X = df[feature_cols].values.astype(np.float32)
    y = df[target_col].values.astype(np.float32)
    return X, y


def fit_scaler(X_train: np.ndarray) -> StandardScaler:
    """
    Fit scaler on TRAINING data only.
    NEVER fit on val/test — only transform.
    """
    scaler = StandardScaler()
    scaler.fit(X_train)
    return scaler
