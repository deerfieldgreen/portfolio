-- Migrate mr_regime_states from MergeTree to ReplacingMergeTree(created_at)
-- so ClickHouse keeps only the newest row per (pair, timeframe, timestamp).

-- Create new table with ReplacingMergeTree engine
CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.mr_regime_states_v2 AS ${CLICKHOUSE_DATABASE}.mr_regime_states
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, timestamp)
SETTINGS index_granularity = 8192;

-- Copy deduplicated data
INSERT INTO ${CLICKHOUSE_DATABASE}.mr_regime_states_v2
SELECT * FROM ${CLICKHOUSE_DATABASE}.mr_regime_states FINAL;

-- Swap tables
RENAME TABLE
  ${CLICKHOUSE_DATABASE}.mr_regime_states TO ${CLICKHOUSE_DATABASE}.mr_regime_states_old,
  ${CLICKHOUSE_DATABASE}.mr_regime_states_v2 TO ${CLICKHOUSE_DATABASE}.mr_regime_states;
