"""
Enrich process-data output before training: z-score, PCA on macro, SMA/EMA(30,50,100,200), skew/kurtosis.
Fit on each run (no persisted fit). Output enriched CSV + PCA metadata JSON for train step.
"""

import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_FEATURE_COLS = ["log_return", "volatility", "rsi", "macd", "atr"]


def load_config(config_path: Optional[str] = None) -> Dict:
    """Load config from config.yaml (container or parent)."""
    base = Path(__file__).parent
    for name in ("config.yaml", "../config.yaml"):
        p = (base / name).resolve()
        if p.exists():
            with open(p, "r") as f:
                return yaml.safe_load(f)
    config_yaml = os.environ.get("CONFIG_YAML", "")
    if config_yaml:
        return yaml.safe_load(config_yaml)
    raise FileNotFoundError("Config file not found")


def zscore_fit_transform(arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Z-score: (x - mean) / std. Returns (transformed, mean, std)."""
    mean = np.nanmean(arr, axis=0)
    std = np.nanstd(arr, axis=0)
    std = np.where(std == 0, 1.0, std)
    out = (arr - mean) / std
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return out, mean, std


def pca_fit_transform(X: np.ndarray, variance_threshold: float = 0.95, max_components: int = 8) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    PCA using NumPy (center, cov, eig). Returns (transformed, components, explained_variance_ratio).
    X: (n_samples, n_features). Returns transformed (n_samples, n_components).
    """
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    mean = np.mean(X, axis=0)
    X_centered = X - mean
    n, d = X_centered.shape
    if n < 2 or d < 1:
        return np.zeros((n, min(max_components, d))), np.eye(d, min(max_components, d)), np.zeros(min(max_components, d))
    # Covariance (sample)
    cov = (X_centered.T @ X_centered) / (n - 1) if n > 1 else np.eye(d) * 1e-6
    cov = np.atleast_2d(cov)
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return np.zeros((n, min(max_components, d))), np.eye(d, min(max_components, d)), np.zeros(min(max_components, d))
    # Descending order
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    total_var = np.sum(eigenvalues)
    if total_var <= 0:
        total_var = 1.0
    explained = eigenvalues / total_var
    cumvar = np.cumsum(explained)
    k = int(np.searchsorted(cumvar, variance_threshold)) + 1
    k = min(max(1, k), max_components, d)
    components = eigenvectors[:, :k]  # (d, k)

    # Standardize PCA sign convention: largest absolute loading per component is positive.
    # This ensures consistent PC direction across runs.
    for j in range(k):
        max_abs_idx = np.argmax(np.abs(components[:, j]))
        if components[max_abs_idx, j] < 0:
            components[:, j] *= -1

    transformed = X_centered @ components  # (n, k)
    return transformed, components, explained[:k]


def sma_ema_for_series(series: pd.Series, windows: List[int]) -> pd.DataFrame:
    """Compute SMA and EMA for each window. Returns DataFrame with columns like col_sma30, col_ema30."""
    out = {}
    for w in windows:
        out[f"sma{w}"] = series.rolling(window=w, min_periods=1).mean()
        out[f"ema{w}"] = series.ewm(span=w, adjust=False).mean()
    return pd.DataFrame(out)


def enrich(df: pd.DataFrame, config: Dict, output_dir: Optional[str] = None) -> pd.DataFrame:
    """
    Z-score base + macro; PCA on macro; SMA/EMA(30,50,100,200) on PCs; skew/kurtosis per PC.
    All fit on this run's data. Writes PCA metadata JSON to output_dir.
    """
    enrichment_config = config.get("enrichment", {})
    variance_threshold = float(enrichment_config.get("pca_variance_threshold", 0.95))
    max_components = int(enrichment_config.get("pca_max_components", 5))
    windows = list(enrichment_config.get("sma_ema_windows", [30, 50, 100, 200]))

    base_cols = [c for c in BASE_FEATURE_COLS if c in df.columns]
    macro_cols = [c for c in df.columns if c.endswith("_us")]
    if not base_cols:
        logger.warning("No base feature columns found")
    if not macro_cols:
        logger.warning("No macro columns found; PCA will be skipped")

    # 1) Z-score base features
    df = df.copy()
    z_means = {}
    z_stds = {}
    for col in base_cols:
        arr = df[col].values.astype(float)
        z, mean, std = zscore_fit_transform(arr.reshape(-1, 1))
        df[f"{col}_z"] = z.ravel()
        z_means[col] = float(mean[0])
        z_stds[col] = float(std[0])

    # 2) Z-score macro, then PCA on z-scored macro
    if macro_cols:
        macro_arr = df[macro_cols].values.astype(float)
        macro_z, macro_means, macro_stds = zscore_fit_transform(macro_arr)
        for i, col in enumerate(macro_cols):
            df[f"{col}_z"] = macro_z[:, i]
            z_means[col] = float(macro_means[i])
            z_stds[col] = float(macro_stds[i])

        transformed, components, explained = pca_fit_transform(
            macro_z, variance_threshold=variance_threshold, max_components=max_components
        )
        n_components = transformed.shape[1]
        logger.info(f"PCA: {n_components} components, explained variance ratio: {explained}")

        for i in range(n_components):
            df[f"pc{i + 1}"] = transformed[:, i]

        # 3) SMA/EMA on each PC series
        for i in range(n_components):
            pc_name = f"pc{i + 1}"
            sma_ema_df = sma_ema_for_series(df[pc_name], windows)
            for c in sma_ema_df.columns:
                df[f"{pc_name}_{c}"] = sma_ema_df[c].values

        # 4) Rolling skew and kurtosis per PC (window=60)
        for i in range(n_components):
            s = df[f"pc{i + 1}"]
            df[f"pc{i + 1}_skew"] = s.rolling(window=60, min_periods=1).skew()
            df[f"pc{i + 1}_kurtosis"] = s.rolling(window=60, min_periods=1).kurt()

        # 5) Serialize PCA metadata to JSON
        if output_dir:
            pca_metadata = {
                "timestamp": datetime.utcnow().isoformat(),
                "n_components": n_components,
                "explained_variance_ratio": explained.tolist(),
                "cumulative_variance": float(np.cumsum(explained)[-1]),
                "z_means": z_means,
                "z_stds": z_stds,
            }
            pca_path = Path(output_dir) / "pca_metadata.json"
            try:
                with open(pca_path, "w") as f:
                    json.dump(pca_metadata, f, indent=2)
                logger.info(f"Wrote PCA metadata to {pca_path}")
            except Exception as e:
                logger.warning(f"Failed to write PCA metadata: {e}")
    else:
        n_components = 0

    # Fill NaN in new columns (e.g. leading SMA/EMA)
    new_cols = [c for c in df.columns if c.endswith("_z") or c.startswith("pc")]
    if new_cols:
        df[new_cols] = df[new_cols].ffill().bfill().fillna(0)

    logger.info(f"Enrichment added {len(new_cols)} columns ({n_components} PCs)")
    return df


def main() -> int:
    input_path = os.environ.get("INPUT_PATH", "")
    output_path = os.environ.get("OUTPUT_PATH", "")
    if not input_path or not output_path:
        logger.error("INPUT_PATH and OUTPUT_PATH required")
        return 1
    if not Path(input_path).exists():
        logger.error(f"Input file not found: {input_path}")
        return 1

    logger.info(f"Loading {input_path}")
    df = pd.read_csv(input_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    config = load_config()
    output_dir = str(Path(output_path).parent)
    df = enrich(df, config, output_dir=output_dir)

    df.to_csv(output_path, index=False)
    logger.info(f"Wrote enriched data to {output_path} ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
