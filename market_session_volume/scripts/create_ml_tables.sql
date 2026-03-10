-- ML insight tables for market session volume pipeline.
-- Database from env: CLICKHOUSE_DATABASE (substituted by run_create_ml_tables.py).
-- Run as ClickHouse admin. App user needs INSERT on these tables.

CREATE DATABASE IF NOT EXISTS ${CLICKHOUSE_DATABASE};

CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.msv_pair_clusters (
    pair String,
    timeframe String,
    cluster_id Int32,
    generated_at DateTime
) ENGINE = MergeTree()
ORDER BY (pair, timeframe, generated_at)
TTL generated_at + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.msv_hourly_forecasts (
    pair String,
    timeframe String,
    hour_gmt Int32,
    next_volume_forecast Float64,
    generated_at DateTime
) ENGINE = MergeTree()
ORDER BY (pair, timeframe, hour_gmt, generated_at)
TTL generated_at + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_daily (
    pair String,
    timeframe String,
    date Date,
    daily_volume Float64,
    is_anomaly UInt8,
    generated_at DateTime
) ENGINE = MergeTree()
ORDER BY (pair, timeframe, date, generated_at)
TTL generated_at + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_hourly (
    pair String,
    timeframe String,
    date Date,
    hour_gmt Int32,
    hourly_volume Float64,
    is_anomaly UInt8,
    generated_at DateTime
) ENGINE = MergeTree()
ORDER BY (pair, timeframe, date, hour_gmt, generated_at)
TTL generated_at + INTERVAL 90 DAY DELETE;

CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.msv_volatility_correlations (
    pair String,
    timeframe String,
    correlation Float64,
    generated_at DateTime
) ENGINE = MergeTree()
ORDER BY (pair, timeframe, generated_at)
TTL generated_at + INTERVAL 90 DAY DELETE;

-- Migrate existing tables: add timeframe column and TTL
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_pair_clusters ADD COLUMN IF NOT EXISTS timeframe String DEFAULT '';
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_hourly_forecasts ADD COLUMN IF NOT EXISTS timeframe String DEFAULT '';
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_daily ADD COLUMN IF NOT EXISTS timeframe String DEFAULT '';
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_hourly ADD COLUMN IF NOT EXISTS timeframe String DEFAULT '';
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volatility_correlations ADD COLUMN IF NOT EXISTS timeframe String DEFAULT '';

ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_pair_clusters MODIFY TTL generated_at + INTERVAL 90 DAY DELETE;
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_hourly_forecasts MODIFY TTL generated_at + INTERVAL 90 DAY DELETE;
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_daily MODIFY TTL generated_at + INTERVAL 90 DAY DELETE;
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volume_anomalies_hourly MODIFY TTL generated_at + INTERVAL 90 DAY DELETE;
ALTER TABLE ${CLICKHOUSE_DATABASE}.msv_volatility_correlations MODIFY TTL generated_at + INTERVAL 90 DAY DELETE;
