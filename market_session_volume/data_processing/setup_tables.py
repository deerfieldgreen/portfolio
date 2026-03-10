#!/usr/bin/env python3
"""Create ClickHouse tables for market session volume pipeline (idempotent)."""
import os
import sys
import logging

import clickhouse_connect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS {db}.msv_pair_clusters (
        pair String,
        timeframe String,
        cluster_id Int32,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
    """CREATE TABLE IF NOT EXISTS {db}.msv_hourly_forecasts (
        pair String,
        timeframe String,
        hour_gmt Int32,
        next_volume_forecast Float64,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, hour_gmt, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
    """CREATE TABLE IF NOT EXISTS {db}.msv_volume_anomalies_daily (
        pair String,
        timeframe String,
        date Date,
        daily_volume Float64,
        is_anomaly UInt8,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, date, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
    """CREATE TABLE IF NOT EXISTS {db}.msv_volume_anomalies_hourly (
        pair String,
        timeframe String,
        date Date,
        hour_gmt Int32,
        hourly_volume Float64,
        is_anomaly UInt8,
        anomaly_score Float64 DEFAULT 0.0,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, date, hour_gmt, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
    """CREATE TABLE IF NOT EXISTS {db}.msv_volatility_correlations (
        pair String,
        timeframe String,
        correlation Float64,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
    """CREATE TABLE IF NOT EXISTS {db}.msv_session_baselines (
        pair         String,
        timeframe    String,
        session_name String,
        mean_volume  Float64,
        std_volume   Float64,
        mean_atr     Float64,
        std_atr      Float64,
        generated_at DateTime
    ) ENGINE = MergeTree() ORDER BY (pair, timeframe, session_name, generated_at)
    TTL generated_at + INTERVAL 90 DAY DELETE""",
]

# ALTER statements to add timeframe column and TTL to existing tables
ALTER_SQL = [
    "ALTER TABLE {db}.msv_pair_clusters ADD COLUMN IF NOT EXISTS timeframe String DEFAULT ''",
    "ALTER TABLE {db}.msv_hourly_forecasts ADD COLUMN IF NOT EXISTS timeframe String DEFAULT ''",
    "ALTER TABLE {db}.msv_volume_anomalies_daily ADD COLUMN IF NOT EXISTS timeframe String DEFAULT ''",
    "ALTER TABLE {db}.msv_volume_anomalies_hourly ADD COLUMN IF NOT EXISTS timeframe String DEFAULT ''",
    "ALTER TABLE {db}.msv_volume_anomalies_hourly ADD COLUMN IF NOT EXISTS anomaly_score Float64 DEFAULT 0.0",
    "ALTER TABLE {db}.msv_volatility_correlations ADD COLUMN IF NOT EXISTS timeframe String DEFAULT ''",
    "ALTER TABLE {db}.msv_pair_clusters MODIFY TTL generated_at + INTERVAL 90 DAY DELETE",
    "ALTER TABLE {db}.msv_hourly_forecasts MODIFY TTL generated_at + INTERVAL 90 DAY DELETE",
    "ALTER TABLE {db}.msv_volume_anomalies_daily MODIFY TTL generated_at + INTERVAL 90 DAY DELETE",
    "ALTER TABLE {db}.msv_volume_anomalies_hourly MODIFY TTL generated_at + INTERVAL 90 DAY DELETE",
    "ALTER TABLE {db}.msv_volatility_correlations MODIFY TTL generated_at + INTERVAL 90 DAY DELETE",
]


def main():
    db = os.environ.get("CLICKHOUSE_DATABASE", "oanda_data_statistics")
    logger.info("Setting up msv_ tables in %s", db)

    client = clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        username=os.environ["CLICKHOUSE_USERNAME"],
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        secure=os.environ.get("CLICKHOUSE_SECURE", "").lower() in ("1", "true", "yes"),
    )
    logger.info("Connected to ClickHouse")

    client.command(f"CREATE DATABASE IF NOT EXISTS {db}")
    logger.info("OK: CREATE DATABASE IF NOT EXISTS %s", db)

    for sql in TABLES_SQL:
        stmt = sql.format(db=db)
        client.command(stmt)
        table_name = stmt.split("EXISTS")[-1].split("(")[0].strip()
        logger.info("OK: %s", table_name)

    for sql in ALTER_SQL:
        stmt = sql.format(db=db)
        try:
            client.command(stmt)
            logger.info("OK: %s", stmt.split("TABLE")[-1].split("ADD")[0].split("MODIFY")[0].strip())
        except Exception as e:
            logger.warning("ALTER skipped (may already exist): %s", e)

    logger.info("Table setup complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
