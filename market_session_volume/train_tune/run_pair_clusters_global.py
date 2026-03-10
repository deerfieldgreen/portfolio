#!/usr/bin/env python3
"""
Global pair-clusters task: one KMeans fit per timeframe over all pairs.
Writes workspace/pair_clusters_{timeframe}.json for collect to merge.
Invoked by Argo pair-clusters-global-step (one task per timeframe).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from train_tune.generate_volume_statistics import (
    VolumeStatisticsGenerator,
    TuningConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    timeframe = os.getenv("TIMEFRAME", "").strip().upper()
    if not timeframe or timeframe not in ("H1", "H4", "D"):
        logger.error("TIMEFRAME must be H1, H4, or D")
        sys.exit(1)

    days_look_back_raw = os.getenv("DAYS_LOOK_BACK", "")
    days_back = int(days_look_back_raw) if days_look_back_raw.strip() else None
    workspace_dir = Path(os.getenv("WORKSPACE_DIR", "/workspace"))

    cfg = TuningConfig(
        k_range=(2, 10),
        min_silhouette=0.3,
    )

    gen = VolumeStatisticsGenerator()
    gen.connect_clickhouse()
    if not gen._discover_schema():
        logger.error("Schema discovery failed")
        sys.exit(1)
    gen.set_timeframe(timeframe)
    logger.info("Running global pair clusters for timeframe=%s, days_back=%s", timeframe, days_back)

    hourly_df = gen._query_all_pairs_hourly(days_back)
    if hourly_df.empty:
        logger.warning("No hourly data for timeframe=%s", timeframe)
        pair_clusters = {}
    else:
        pair_clusters = VolumeStatisticsGenerator._compute_pair_clusters(
            hourly_df,
            tune_k=True,
            k_range=cfg.k_range,
            min_silhouette=cfg.min_silhouette,
        )

    out = {"pair_clusters": pair_clusters, "timeframe": timeframe}
    workspace_dir.mkdir(parents=True, exist_ok=True)
    out_path = workspace_dir / f"pair_clusters_{timeframe}.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    logger.info("Wrote %s with %d pairs", out_path, len(pair_clusters))


if __name__ == "__main__":
    main()
