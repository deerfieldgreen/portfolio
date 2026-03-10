#!/usr/bin/env python3
"""
Single training task: model + pair + timeframe (+ hour for hourly models).
Each task runs one model for one (pair, timeframe) or (pair, timeframe, hour).
Tuning (n_clusters, contamination, n_estimators, ARIMA order) is done at this
granular level—each task tunes independently for its (model, pair, timeframe[, hour]).
Outputs to workspace for collect step.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from train_tune.generate_volume_statistics import (
    VolumeStatisticsGenerator,
    TuningConfig,
    DEFAULT_PAIRS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


def _json_default(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def run_pair_clusters(
    gen: VolumeStatisticsGenerator,
    pair: str,
    timeframe: str,
    days_back: int | None,
    cfg: TuningConfig,
) -> dict:
    """Run KMeans for one pair (fits on all pairs, outputs this pair only)."""
    hourly_df = gen._query_all_pairs_hourly(days_back)
    if hourly_df.empty:
        return {}
    pair_clusters = VolumeStatisticsGenerator._compute_pair_clusters(
        hourly_df,
        tune_k=True,
        k_range=cfg.k_range,
        min_silhouette=cfg.min_silhouette,
    )
    if pair not in pair_clusters:
        return {}
    return {"pair_clusters": {pair: pair_clusters[pair]}}


def run_daily_if(
    gen: VolumeStatisticsGenerator,
    pair: str,
    timeframe: str,
    days_back: int | None,
    cfg: TuningConfig,
) -> dict:
    """Run daily Isolation Forest for one pair."""
    daily_df = gen._query_daily_totals(days_back)
    pair_df = daily_df[daily_df["pair"] == pair] if not daily_df.empty else daily_df
    if pair_df.empty or len(pair_df) < 3:
        return {}
    out = VolumeStatisticsGenerator._compute_volume_anomalies(
        pair_df,
        tune=True,
        tuning_config=cfg,
    )
    return {"volume_anomalies": out} if out else {}


def run_hourly_if(
    gen: VolumeStatisticsGenerator,
    pair: str,
    timeframe: str,
    hour: int,
    days_back: int | None,
    cfg: TuningConfig,
) -> dict:
    """Run hourly Isolation Forest for one (pair, hour). Filters to that hour."""
    from sklearn.ensemble import IsolationForest

    hourly_df = gen._query_hourly_totals(days_back)
    if hourly_df.empty:
        return {}
    pair_df = hourly_df[hourly_df["pair"] == pair].copy()
    pair_df["date"] = pd.to_datetime(pair_df["date"])
    pair_df["hour_gmt"] = pair_df["hour_gmt"].astype(int)
    hour_sub = pair_df[pair_df["hour_gmt"] == hour].sort_values("date")
    if len(hour_sub) < 3:
        return {}
    hour_sub = hour_sub.copy()
    hour_sub["lag1"] = hour_sub["hourly_volume"].shift(1)
    hour_sub["dow"] = hour_sub["date"].dt.dayofweek
    features_df = hour_sub[["hourly_volume", "lag1", "dow"]].dropna()
    if len(features_df) < 3:
        return {}
    X = features_df.values.astype(float)
    c, n = VolumeStatisticsGenerator._tune_isolation_forest(
        X, cfg.contamination_grid, cfg.n_estimators_grid
    )
    model = IsolationForest(contamination=c, n_estimators=n, random_state=42).fit(X)
    pred = model.predict(X)
    scores = model.score_samples(X)
    records = []
    for i, idx in enumerate(features_df.index):
        row = hour_sub.loc[idx]
        records.append({
            "date": row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
            "hour_gmt": int(row["hour_gmt"]),
            "hourly_volume": float(row["hourly_volume"]),
            "is_anomaly": bool(pred[i] == -1),
            "anomaly_score": float(scores[i]),
        })
    return {"hourly_volume_anomalies": {pair: records}}


def run_arima(
    gen: VolumeStatisticsGenerator,
    pair: str,
    timeframe: str,
    hour: int,
    days_back: int | None,
    cfg: TuningConfig,
) -> dict:
    """Run ARIMA for one (pair, hour)."""
    hourly_ts_df = gen._query_hourly_timeseries(days_back)
    if hourly_ts_df.empty:
        return {}
    grp = hourly_ts_df[
        (hourly_ts_df["pair"] == pair) & (hourly_ts_df["hour_gmt"] == hour)
    ].sort_values("date")
    if len(grp) < 5:
        return {}
    ser = grp.set_index("date")["total_volume"]
    fcast = VolumeStatisticsGenerator._fit_arima_forecast(
        ser,
        tune=True,
        seasonal_period=cfg.seasonal_period,
        train_ratio=cfg.train_ratio,
        use_exog_dow=cfg.arima_use_exog_dow,
    )
    if fcast is None:
        return {}
    key = f"{pair}|{hour}"
    return {"hourly_forecasts": {key: {"pair": pair, "hour_gmt": hour, "next_volume_forecast": fcast}}}


def main():
    model_type = os.getenv("MODEL_TYPE", "").strip().lower()
    pair = os.getenv("PAIR", "").strip()
    timeframe = os.getenv("DATASET_ID", os.getenv("TIMEFRAME", "")).strip()
    hour_s = os.getenv("HOUR", "")
    workspace_dir = Path(os.getenv("WORKSPACE_DIR", "/workspace"))

    if not model_type or not pair or not timeframe:
        logger.error("MODEL_TYPE, PAIR, DATASET_ID (timeframe) required")
        sys.exit(1)

    hour = int(hour_s) if hour_s.strip() else None
    if model_type in ("hourly_if", "arima") and hour is None:
        logger.error("HOUR required for model types: hourly_if, arima")
        sys.exit(1)

    days_back_raw = os.getenv("DAYS_LOOK_BACK", "")
    days_back = int(days_back_raw) if days_back_raw.strip() else None
    cfg = TuningConfig(
        k_range=(2, 10),
        min_silhouette=0.3,
        contamination_grid=(0.05, 0.075, 0.1, 0.125, 0.15),
        n_estimators_grid=(50, 100, 150),
        seasonal_period=5,
        train_ratio=0.8,
    )

    gen = VolumeStatisticsGenerator()
    gen.connect_clickhouse()
    if not gen._discover_schema():
        logger.error("Schema discovery failed")
        sys.exit(1)
    # Restrict to this dataset's timeframe (e.g. H1 from USDJPY_H1)
    if "_" in timeframe:
        tf = timeframe.split("_")[-1].upper()
        if tf in ("H1", "H4", "D"):
            gen.set_timeframe(tf)
            logger.info("Filtering OHLCV to timeframe=%s", tf)

    result: dict = {}
    if model_type == "pair_clusters":
        result = run_pair_clusters(gen, pair, timeframe, days_back, cfg)
    elif model_type == "daily_if":
        result = run_daily_if(gen, pair, timeframe, days_back, cfg)
    elif model_type == "hourly_if":
        result = run_hourly_if(gen, pair, timeframe, hour, days_back, cfg)
    elif model_type == "arima":
        result = run_arima(gen, pair, timeframe, hour, days_back, cfg)
    else:
        logger.error("Unknown MODEL_TYPE: %s", model_type)
        sys.exit(1)

    out = {
        "model_type": model_type,
        "pair": pair,
        "timeframe": timeframe,
        "hour": hour,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }

    workspace_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{hour}" if hour is not None else ""
    out_path = workspace_dir / f"{timeframe}_{model_type}_{pair}{suffix}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=_json_default)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
