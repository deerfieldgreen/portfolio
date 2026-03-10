-- Create materialized view for current regimes (latest regime per pair/timeframe)
CREATE MATERIALIZED VIEW IF NOT EXISTS ${CLICKHOUSE_DATABASE}.mr_mv_current_regimes
ENGINE = ReplacingMergeTree(timestamp)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe)
AS
SELECT
    pair,
    timeframe,
    argMax(timestamp, timestamp) as timestamp,
    argMax(regime_state, timestamp) as regime_state,
    argMax(state_prob_0, timestamp) as state_prob_0,
    argMax(state_prob_1, timestamp) as state_prob_1,
    argMax(state_prob_2, timestamp) as state_prob_2,
    argMax(confidence_score, timestamp) as confidence_score,
    argMax(mean_returns_per_state, timestamp) as mean_returns_per_state,
    argMax(volatility_per_state, timestamp) as volatility_per_state,
    argMax(log_return, timestamp) as log_return,
    argMax(volatility, timestamp) as volatility,
    argMax(regime_duration, timestamp) as regime_duration
FROM ${CLICKHOUSE_DATABASE}.mr_regime_states
GROUP BY pair, timeframe;

-- Create materialized view for regime statistics (summary by regime state)
CREATE MATERIALIZED VIEW IF NOT EXISTS ${CLICKHOUSE_DATABASE}.mr_mv_regime_statistics
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, regime_state)
AS
SELECT
    pair,
    timeframe,
    regime_state,
    toStartOfDay(timestamp) as date,
    count() as occurrence_count,
    avg(log_return) as avg_return,
    stddevPop(log_return) as volatility,
    avg(confidence_score) as avg_confidence,
    avg(regime_duration) as avg_duration
FROM ${CLICKHOUSE_DATABASE}.mr_regime_states
GROUP BY pair, timeframe, regime_state, date;
