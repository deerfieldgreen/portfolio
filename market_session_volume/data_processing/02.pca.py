import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# ────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────
MLFLOW_TRACKING_URI = "http://localhost:5000"
EXPERIMENT_NAME     = "USDJPY_H1_PCA_Exploration"

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
mlflow.set_experiment(EXPERIMENT_NAME)

# ────────────────────────────────────────────────
# 1. Load & filter data (same as before – adjust path if needed)
# ────────────────────────────────────────────────
df_ohlcv = pd.read_csv(
    "sample_data.txt", sep=None, engine="python", comment="=",
    header=None, skipinitialspace=True,
    names=["pair", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]
)

ohlcv = df_ohlcv[
    (df_ohlcv["pair"] == "USD_JPY") &
    (df_ohlcv["timeframe"] == "H1")
].copy().reset_index(drop=True)

print(f"Loaded {len(ohlcv)} USD_JPY H1 candles")

# ────────────────────────────────────────────────
# 2. Minimal feature set
# ────────────────────────────────────────────────
ohlcv["range"]      = ohlcv["high"] - ohlcv["low"]
ohlcv["body"]       = abs(ohlcv["close"] - ohlcv["open"])
ohlcv["log_return"] = np.log(ohlcv["close"] / ohlcv["close"].shift(1))
ohlcv["direction"]  = np.sign(ohlcv["close"] - ohlcv["open"])

features = ohlcv[["close", "volume", "range", "body", "log_return", "direction"]].dropna().reset_index(drop=True)

print(f"Feature matrix shape: {features.shape}")

# ────────────────────────────────────────────────
# 3. Start MLflow run & log everything inside context
# ────────────────────────────────────────────────
with mlflow.start_run(run_name="PCA-baseline-features-v1") as run:

    # ── Log basic run info ───────────────────────────────────────
    mlflow.log_param("pair",        "USD_JPY")
    mlflow.log_param("timeframe",   "H1")
    mlflow.log_param("n_candles",   len(ohlcv))
    mlflow.log_param("n_features",  features.shape[1])
    mlflow.log_param("n_samples",   features.shape[0])

    # ── Standardize ──────────────────────────────────────────────
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(features)

    mlflow.sklearn.log_model(scaler, "scaler")           # optional but useful

    # ── Run PCA ──────────────────────────────────────────────────
    pca = PCA()
    X_pca = pca.fit_transform(X_scaled)

    # ── Log PCA parameters & diagnostics ─────────────────────────
    mlflow.log_param("pca_whiten", pca.whiten)

    explained_var     = pca.explained_variance_ratio_
    cum_explained_var = np.cumsum(explained_var)

    for i, ratio in enumerate(explained_var, 1):
        mlflow.log_metric(f"explained_variance_pc{i:02d}", ratio)

    mlflow.log_metric("explained_variance_cum_80pct",  next((v for v in cum_explained_var if v >= 0.80), 1.0))
    mlflow.log_metric("n_components_90pct",            next((i for i,v in enumerate(cum_explained_var,1) if v >= 0.90), len(explained_var)))

    # ── Log cumulative variance at selected points ───────────────
    thresholds = [0.70, 0.80, 0.90, 0.95]
    for thresh in thresholds:
        n = next((i for i,v in enumerate(cum_explained_var,1) if v >= thresh), None)
        if n:
            mlflow.log_metric(f"n_components_for_{int(thresh*100)}pct", n)

    # ── Save & log scree + cumulative plot ───────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    ax1.bar(range(1, len(explained_var)+1), explained_var, alpha=0.7)
    ax1.set(xlabel="Principal Component", ylabel="Explained Variance Ratio", title="Scree Plot")

    ax2.plot(range(1, len(cum_explained_var)+1), cum_explained_var, marker="o", linestyle="--")
    ax2.axhline(y=0.8, color="r", linestyle=":", label="80%")
    ax2.axhline(y=0.9, color="darkred", linestyle=":", label="90%")
    ax2.set(xlabel="Number of Components", ylabel="Cumulative Explained Variance", title="Cumulative Variance")
    ax2.legend()

    plt.tight_layout()
    fig.savefig("pca_scree_cumulative.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    mlflow.log_artifact("pca_scree_cumulative.png", artifact_path="plots")

    # ── Optional: log first few rows of transformed data ─────────
    pd.DataFrame(
        X_pca[:, :min(5, X_pca.shape[1])],
        columns=[f"PC{i+1}" for i in range(min(5, X_pca.shape[1]))]
    ).head(200).to_csv("pca_transformed_head.csv", index=False)

    mlflow.log_artifact("pca_transformed_head.csv", artifact_path="transformed")

    print(f"Run completed → {run.info.run_id}")
    print(f"View in UI:   {MLFLOW_TRACKING_URI}/#/experiments/{run.info.experiment_id}/runs/{run.info.run_id}")