#!/usr/bin/env python3
"""
Market Sessions ML Training Pipeline with MLflow integration.
Trains KMeans, IsolationForest, and ARIMA models on volume data.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import mlflow
import mlflow.sklearn
import mlflow.pyfunc
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest

# Import volume statistics generator (train_tune internal)
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


class MLflowVolumeAnalyzer:
    """Wrapper that logs all ML artifacts to MLflow."""

    def __init__(self, experiment_name: str = "market-sessions-volume-analysis"):
        try:
            mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000"))
            mlflow.set_experiment(experiment_name)
            logger.info(f"MLflow tracking URI: {mlflow.get_tracking_uri()}")
        except Exception as e:
            logger.error(f"Failed to initialize MLflow: {e}")
            raise
        self.generator = VolumeStatisticsGenerator()
        self.run_id: str | None = None

    def train_and_log(
        self,
        pairs: list[str],
        days_back: int | None,
        tune_hyperparams: bool,
        tuning_config: TuningConfig,
    ) -> Dict[str, Any]:
        """Train all models and log to MLflow."""

        with mlflow.start_run(run_name=f"volume_analysis_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}") as run:
            self.run_id = run.info.run_id

            # Log parameters
            mlflow.log_params({
                "pairs": ",".join(pairs),
                "days_back": days_back if days_back else "all",
                "tune_hyperparams": tune_hyperparams,
                "k_range": f"{tuning_config.k_range[0]}-{tuning_config.k_range[1]}",
                "min_silhouette": tuning_config.min_silhouette,
                "seasonal_period": tuning_config.seasonal_period,
                "workers": tuning_config.workers,
            })

            # Generate statistics
            logger.info("Generating volume statistics with ML models...")
            stats = self.generator.generate_session_statistics(
                pairs=pairs,
                days_back=days_back,
                tune_hyperparams=tune_hyperparams,
                tuning_config=tuning_config,
            )

            # Log summary metrics
            summary = stats.get("summary", {})

            # KMeans cluster count
            pair_clusters = summary.get("pair_clusters", {})
            if pair_clusters:
                n_clusters = len(set(pair_clusters.values()))
                mlflow.log_metric("kmeans_n_clusters", n_clusters)
                mlflow.log_metric("kmeans_pairs_clustered", len(pair_clusters))

            # Isolation Forest anomaly counts
            volume_anomalies = summary.get("volume_anomalies", {})
            if volume_anomalies:
                total_anomalies = sum(
                    sum(1 for d in days if d.get("is_anomaly"))
                    for days in volume_anomalies.values()
                )
                mlflow.log_metric("if_daily_total_anomalies", total_anomalies)
                mlflow.log_metric("if_daily_pairs_analyzed", len(volume_anomalies))

            hourly_anomalies = summary.get("hourly_volume_anomalies", {})
            if hourly_anomalies:
                total_hourly_anomalies = sum(
                    sum(1 for h in hours if h.get("is_anomaly"))
                    for hours in hourly_anomalies.values()
                )
                mlflow.log_metric("if_hourly_total_anomalies", total_hourly_anomalies)

            # ARIMA forecast count
            hourly_forecasts = summary.get("hourly_forecasts", {})
            if hourly_forecasts:
                mlflow.log_metric("arima_forecasts_generated", len(hourly_forecasts))

                # Log average forecast value per pair
                pair_forecasts = {}
                for key, val in hourly_forecasts.items():
                    pair = val.get("pair")
                    forecast = val.get("next_volume_forecast", 0)
                    if pair not in pair_forecasts:
                        pair_forecasts[pair] = []
                    pair_forecasts[pair].append(forecast)

                for pair, forecasts in pair_forecasts.items():
                    avg = np.mean(forecasts)
                    mlflow.log_metric(f"arima_avg_forecast_{pair}", avg)

            # Save statistics JSON as artifact
            stats_path = Path("/tmp/volume_statistics.json")
            with open(stats_path, "w") as f:
                json.dump(stats, f, indent=2, default=str)
            mlflow.log_artifact(str(stats_path), artifact_path="statistics")

            # Persist ML insights to ClickHouse
            self.generator.persist_ml_insights_to_clickhouse(stats)

            # Log models as MLflow models
            self._log_models_to_mlflow(stats, tuning_config)

            logger.info(f"✅ MLflow run completed: {self.run_id}")

            return stats

    def _log_models_to_mlflow(self, stats: Dict[str, Any], config: TuningConfig):
        """Log trained models to MLflow Model Registry."""
        summary = stats.get("summary", {})

        # Log KMeans model (if tuned)
        pair_clusters = summary.get("pair_clusters")
        if pair_clusters:
            # Reconstruct KMeans from cluster assignments
            # (In production, you'd save the actual fitted model)
            mlflow.log_dict(pair_clusters, "kmeans_cluster_assignments.json")

        # Log Isolation Forest parameters (cached)
        cache_path = config.cache_path
        if cache_path and cache_path.exists():
            mlflow.log_artifact(str(cache_path), artifact_path="model_cache")

        # Log ARIMA forecasts as custom model
        hourly_forecasts = summary.get("hourly_forecasts", {})
        if hourly_forecasts:
            mlflow.log_dict(hourly_forecasts, "arima_forecasts.json")


def main():
    try:
        parser = argparse.ArgumentParser(description="Market sessions ML training with MLflow")
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--pairs", type=str, default=None)
        parser.add_argument("--tune-hyperparams", action="store_true", default=True)
        parser.add_argument("--workers", type=int, default=4)
        parser.add_argument("--cache", type=str, default="/workspace/ml_cache.json")
        parser.add_argument("--k-range", type=str, default="2-10")
        parser.add_argument("--seasonal-period", type=int, default=5)
        parser.add_argument("--mlflow-tracking-uri", type=str, 
                           default=os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service:5000"),
                           help="MLflow tracking server URI")
        parser.add_argument("--clickhouse-host", type=str,
                           default=os.getenv("CLICKHOUSE_HOST"),
                           help="ClickHouse host for persistence")
        args = parser.parse_args()

        # Parse pairs
        if args.pairs:
            pairs = [p.strip() for p in args.pairs.strip('[]"').split(",")]
        else:
            pairs = DEFAULT_PAIRS

        # Parse k-range
        k_min, k_max = map(int, args.k_range.split("-"))

        # Tuning config
        tuning_config = TuningConfig(
            k_range=(k_min, k_max),
            min_silhouette=0.3,
            seasonal_period=args.seasonal_period,
            cache_path=Path(args.cache) if args.cache else None,
            workers=args.workers,
        )

        # Set MLflow tracking URI if provided
        if args.mlflow_tracking_uri:
            os.environ["MLFLOW_TRACKING_URI"] = args.mlflow_tracking_uri

        # Train and log
        analyzer = MLflowVolumeAnalyzer()
        stats = analyzer.train_and_log(
            pairs=pairs,
            days_back=args.days,
            tune_hyperparams=args.tune_hyperparams,
            tuning_config=tuning_config,
        )

        # Write run ID for Argo
        if analyzer.run_id:
            with open("/tmp/mlflow_run_id.txt", "w") as f:
                f.write(analyzer.run_id)
            logger.info(f"Saved MLflow run ID: {analyzer.run_id}")
        else:
            logger.warning("No MLflow run ID to save")

        with open("/tmp/stats_path.txt", "w") as f:
            f.write("/tmp/volume_statistics.json")

        logger.info(f"Pipeline complete. MLflow run: {analyzer.run_id}")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
