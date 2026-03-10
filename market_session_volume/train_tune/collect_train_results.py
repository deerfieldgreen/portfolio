#!/usr/bin/env python3
"""
Collect partial training results from workspace and merge into full statistics.
Computes volatility (ATR–volume correlation) for this dataset, persists all to ClickHouse,
logs a run to MLflow, and appends run_id for select-register.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import mlflow
from train_tune.generate_volume_statistics import (
    VolumeStatisticsGenerator,
    SESSION_HOURS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _json_default(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _persist_session_baselines(
    gen: VolumeStatisticsGenerator,
    pairs: list[str],
    timeframe: str,
    days_back: int | None,
) -> None:
    """Compute per-session volume and ATR baselines for each pair and insert into msv_session_baselines."""
    import pandas as pd
    from train_tune.generate_volume_statistics import CLICKHOUSE_DATABASE, _safe_float

    saved_tf = gen._timeframe
    gen._timeframe = None  # Baselines should use all available data
    try:
        hourly_df = gen._query_all_pairs_hourly(days_back)
        ohlcv_df = gen._query_ohlcv(days_back) if getattr(gen, "_has_ohlc", False) else pd.DataFrame()
    finally:
        gen._timeframe = saved_tf
    run_ts = datetime.now(timezone.utc)
    rows = []

    for pair in pairs:
        sub = hourly_df[hourly_df["pair"] == pair].copy() if not hourly_df.empty else pd.DataFrame()
        if sub.empty:
            continue
        sub["hour_gmt"] = sub["hour_gmt"].astype(int)

        # Per-session ATR from OHLCV — compute rolling ATR(14) grouped by session hours
        ohlcv_pair = pd.DataFrame()
        if not ohlcv_df.empty and gen._pair_col in ohlcv_df.columns:
            ohlcv_pair = ohlcv_df[ohlcv_df[gen._pair_col] == pair].copy()
            if "hour" not in ohlcv_pair.columns and gen._ts_col in ohlcv_pair.columns:
                ohlcv_pair["hour"] = pd.to_datetime(ohlcv_pair[gen._ts_col]).dt.hour
            # Compute ATR per row: true range
            if gen._has_ohlc and len(ohlcv_pair) > 14:
                high = ohlcv_pair[gen._high_col].astype(float)
                low = ohlcv_pair[gen._low_col].astype(float)
                close_prev = ohlcv_pair[gen._close_col].astype(float).shift(1)
                tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
                ohlcv_pair = ohlcv_pair.copy()
                ohlcv_pair["atr"] = tr.rolling(14).mean()

        session_stats = VolumeStatisticsGenerator._session_stats_from_hourly(sub)

        for session_name, stats in session_stats.items():
            mean_atr, std_atr = 0.0, 0.0
            if not ohlcv_pair.empty and "atr" in ohlcv_pair.columns and "hour" in ohlcv_pair.columns:
                hours = SESSION_HOURS.get(session_name, [])
                session_atr = ohlcv_pair[ohlcv_pair["hour"].isin(hours)]["atr"].dropna()
                if len(session_atr) > 1:
                    mean_atr = _safe_float(session_atr.mean())
                    std_atr = _safe_float(session_atr.std())

            rows.append({
                "pair": pair,
                "timeframe": timeframe,
                "session_name": session_name,
                "mean_volume": _safe_float(stats.get("avg_volume", 0.0)),
                "std_volume": _safe_float(stats.get("std_volume", 0.0)),
                "mean_atr": mean_atr,
                "std_atr": std_atr,
                "generated_at": run_ts,
            })

    if rows:
        df = pd.DataFrame(rows)
        gen._client.insert_df(f"{CLICKHOUSE_DATABASE}.msv_session_baselines", df)
        logger.info("Persisted %d session baselines to ClickHouse", len(rows))
    else:
        logger.warning("No session baselines computed (empty hourly data?)")


def main():
    workspace_dir = Path(os.getenv("WORKSPACE_DIR", "/workspace"))
    dataset = os.getenv("DATASET_ID", "UNKNOWN")
    pairs_param = os.getenv("PAIRS", "EUR_USD,GBP_USD,USD_JPY")
    pairs = [p.strip() for p in pairs_param.split(",") if p.strip()]
    days_look_back_raw = os.getenv("DAYS_LOOK_BACK", "")
    days_analyzed = days_look_back_raw.strip() if days_look_back_raw.strip() else "all"
    days_back_int = int(days_look_back_raw) if days_look_back_raw.strip() else None

    pattern = f"{dataset}_*.json"
    partial_files = list(workspace_dir.glob(pattern))
    if not partial_files:
        logger.warning("No partial files found matching %s in %s", pattern, workspace_dir)
        sys.exit(1)

    pair_clusters: dict[str, int] = {}
    volume_anomalies: dict[str, list] = {}
    hourly_volume_anomalies: dict[str, list] = defaultdict(list)
    hourly_forecasts: dict[str, dict] = {}

    for p in partial_files:
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Skip %s: %s", p.name, e)
            continue
        if "pair_clusters" in data:
            pair_clusters.update(data["pair_clusters"])
        if "volume_anomalies" in data:
            volume_anomalies.update(data["volume_anomalies"])
        if "hourly_volume_anomalies" in data:
            for pair, records in data["hourly_volume_anomalies"].items():
                hourly_volume_anomalies[pair].extend(records)
        if "hourly_forecasts" in data:
            hourly_forecasts.update(data["hourly_forecasts"])

    # Prefer global pair_clusters file (one per timeframe from pair-clusters-global step)
    timeframe = dataset.split("_")[-1].upper() if "_" in dataset else ""
    if timeframe in ("H1", "H4", "D"):
        global_path = workspace_dir / f"pair_clusters_{timeframe}.json"
        if global_path.exists():
            try:
                with open(global_path) as f:
                    global_data = json.load(f)
                full_map = global_data.get("pair_clusters", {})
                # Persist only this collect's pairs to avoid duplicate rows across collect steps
                pair_clusters = {p: full_map[p] for p in pairs if p in full_map}
                logger.info("Using global pair_clusters from %s (%d pairs for this collect)", global_path.name, len(pair_clusters))
            except Exception as e:
                logger.warning("Failed to load %s: %s", global_path, e)

    hourly_volume_anomalies = dict(hourly_volume_anomalies)

    statistics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_analyzed": days_analyzed,
        "pairs": {},
        "summary": {
            "pair_clusters": pair_clusters,
            "volume_anomalies": volume_anomalies,
            "hourly_volume_anomalies": hourly_volume_anomalies,
            "hourly_forecasts": hourly_forecasts,
        },
    }

    gen = VolumeStatisticsGenerator()
    gen.connect_clickhouse()
    if not gen._discover_schema():
        logger.error("Schema discovery failed")
        sys.exit(1)
    # Align timeframe with this dataset (e.g. USDJPY_H1 -> H1) for volatility query
    if "_" in dataset:
        tf = dataset.split("_")[-1].upper()
        if tf in ("H1", "H4", "D"):
            gen.set_timeframe(tf)
    # Compute volatility (ATR–volume correlation) for this dataset and persist with other insights
    try:
        ohlcv_df = gen._query_ohlcv(days_back_int)
        if not ohlcv_df.empty:
            vc_all = VolumeStatisticsGenerator._compute_volatility_correlations(ohlcv_df)
            vc = {p: vc_all[p] for p in pairs if p in vc_all}
            if vc:
                statistics["summary"]["volatility_correlations"] = vc
                logger.info("Computed volatility_correlations for %d pairs", len(vc))
    except Exception as e:
        logger.warning("Volatility computation skipped: %s", e)

    # Compute and persist session baselines (volume mean/std + ATR mean/std per session)
    try:
        _persist_session_baselines(gen, pairs, timeframe, days_back_int)
    except Exception as e:
        logger.warning("Session baselines computation skipped: %s", e)

    gen.persist_ml_insights_to_clickhouse(statistics, timeframe=timeframe)

    stats_path = workspace_dir / f"{dataset}_trained_stats.json"
    with open(stats_path, "w") as f:
        json.dump(statistics, f, indent=2, default=_json_default)
    logger.info("Saved merged stats to %s", stats_path)

    # Log to MLflow for select-register: one run per collect (per dataset_id)
    run_id = None
    try:
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000"))
        mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "market-session-volume"))
        with mlflow.start_run(run_name=f"collect_{dataset}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"):
            run_id = mlflow.active_run().info.run_id
            mlflow.log_params({
                "dataset_id": dataset,
                "pairs": ",".join(pairs),
                "days_analyzed": str(days_analyzed),
            })
            mlflow.log_metrics({
                "kmeans_n_clusters": len(set(pair_clusters.values())) if pair_clusters else 0,
                "kmeans_pairs_clustered": len(pair_clusters),
                "if_daily_pairs_analyzed": len(volume_anomalies),
                "if_hourly_pairs_analyzed": len(hourly_volume_anomalies),
                "arima_forecasts_generated": len(hourly_forecasts),
            })
            mlflow.log_artifact(str(stats_path), artifact_path="statistics")
    except Exception as e:
        logger.warning("MLflow logging failed (run_id not written): %s", e)

    if run_id:
        run_ids_file = workspace_dir / "mlflow_run_ids.txt"
        with open(run_ids_file, "a") as f:
            f.write(run_id + "\n")
        logger.info("Appended run_id %s to %s", run_id, run_ids_file)

    logger.info("pair_clusters=%d, volume_anomalies=%d pairs, hourly_anomalies=%d pairs, hourly_forecasts=%d",
                len(pair_clusters), len(volume_anomalies), len(hourly_volume_anomalies), len(hourly_forecasts))


if __name__ == "__main__":
    main()
