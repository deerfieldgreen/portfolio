-- Materialized view: group by symbol and each hour; for each score compute
-- min, max, avg, stddev, skew, kurtosis. Uses AggregatingMergeTree so blocks merge correctly.
--
-- Run order: drop MV/VIEW/table, create table, create MV, create VIEW, backfill (optional).
-- Use scripts/create_mv_hourly_scores.py to run with config/Doppler.
-- Query final values via VIEW hourly_currency_score_stats (uses -Merge).

-- 1) Drop MV and VIEW first (depend on table), then table.
DROP MATERIALIZED VIEW IF EXISTS news_agent.mv_hourly_currency_score_states;
DROP VIEW IF EXISTS news_agent.hourly_currency_score_stats;
DROP TABLE IF EXISTS news_agent.hourly_currency_score_states;

-- 2) Target table: one row per (hour_bucket, symbol) with aggregate states.
CREATE TABLE IF NOT EXISTS news_agent.hourly_currency_score_states
(
    hour_bucket   DateTime,
    symbol         String,
    article_count  AggregateFunction(count, UInt64),
    -- bearish
    bearish_min    AggregateFunction(min, Float32),
    bearish_max    AggregateFunction(max, Float32),
    bearish_avg    AggregateFunction(avg, Float32),
    bearish_stddev AggregateFunction(stddevPop, Float32),
    bearish_skew   AggregateFunction(skewPop, Float32),
    bearish_kurt   AggregateFunction(kurtPop, Float32),
    -- bullish
    bullish_min    AggregateFunction(min, Float32),
    bullish_max    AggregateFunction(max, Float32),
    bullish_avg    AggregateFunction(avg, Float32),
    bullish_stddev AggregateFunction(stddevPop, Float32),
    bullish_skew   AggregateFunction(skewPop, Float32),
    bullish_kurt   AggregateFunction(kurtPop, Float32),
    -- neutral
    neutral_min    AggregateFunction(min, Float32),
    neutral_max    AggregateFunction(max, Float32),
    neutral_avg    AggregateFunction(avg, Float32),
    neutral_stddev AggregateFunction(stddevPop, Float32),
    neutral_skew   AggregateFunction(skewPop, Float32),
    neutral_kurt   AggregateFunction(kurtPop, Float32),
    -- timeliness
    timeliness_min    AggregateFunction(min, Float32),
    timeliness_max    AggregateFunction(max, Float32),
    timeliness_avg    AggregateFunction(avg, Float32),
    timeliness_stddev AggregateFunction(stddevPop, Float32),
    timeliness_skew   AggregateFunction(skewPop, Float32),
    timeliness_kurt   AggregateFunction(kurtPop, Float32),
    -- volatility_impact
    volatility_impact_min    AggregateFunction(min, Float32),
    volatility_impact_max    AggregateFunction(max, Float32),
    volatility_impact_avg    AggregateFunction(avg, Float32),
    volatility_impact_stddev AggregateFunction(stddevPop, Float32),
    volatility_impact_skew   AggregateFunction(skewPop, Float32),
    volatility_impact_kurt   AggregateFunction(kurtPop, Float32),
    -- confidence
    confidence_min    AggregateFunction(min, Float32),
    confidence_max    AggregateFunction(max, Float32),
    confidence_avg    AggregateFunction(avg, Float32),
    confidence_stddev AggregateFunction(stddevPop, Float32),
    confidence_skew   AggregateFunction(skewPop, Float32),
    confidence_kurt   AggregateFunction(kurtPop, Float32)
)
ENGINE = AggregatingMergeTree()
ORDER BY (hour_bucket, symbol);

-- 3) MV: on INSERT into news_items, aggregate by (hour_bucket, symbol) and emit states.
CREATE MATERIALIZED VIEW news_agent.mv_hourly_currency_score_states
TO news_agent.hourly_currency_score_states
AS
SELECT
    toStartOfHour(timestamp) AS hour_bucket,
    primary_ccy AS symbol,
    countState() AS article_count,
    minState(bearish_prob) AS bearish_min,
    maxState(bearish_prob) AS bearish_max,
    avgState(bearish_prob) AS bearish_avg,
    stddevPopState(bearish_prob) AS bearish_stddev,
    skewPopState(bearish_prob) AS bearish_skew,
    kurtPopState(bearish_prob) AS bearish_kurt,
    minState(bullish_prob) AS bullish_min,
    maxState(bullish_prob) AS bullish_max,
    avgState(bullish_prob) AS bullish_avg,
    stddevPopState(bullish_prob) AS bullish_stddev,
    skewPopState(bullish_prob) AS bullish_skew,
    kurtPopState(bullish_prob) AS bullish_kurt,
    minState(neutral_prob) AS neutral_min,
    maxState(neutral_prob) AS neutral_max,
    avgState(neutral_prob) AS neutral_avg,
    stddevPopState(neutral_prob) AS neutral_stddev,
    skewPopState(neutral_prob) AS neutral_skew,
    kurtPopState(neutral_prob) AS neutral_kurt,
    minState(timeliness) AS timeliness_min,
    maxState(timeliness) AS timeliness_max,
    avgState(timeliness) AS timeliness_avg,
    stddevPopState(timeliness) AS timeliness_stddev,
    skewPopState(timeliness) AS timeliness_skew,
    kurtPopState(timeliness) AS timeliness_kurt,
    minState(volatility_impact) AS volatility_impact_min,
    maxState(volatility_impact) AS volatility_impact_max,
    avgState(volatility_impact) AS volatility_impact_avg,
    stddevPopState(volatility_impact) AS volatility_impact_stddev,
    skewPopState(volatility_impact) AS volatility_impact_skew,
    kurtPopState(volatility_impact) AS volatility_impact_kurt,
    minState(confidence) AS confidence_min,
    maxState(confidence) AS confidence_max,
    avgState(confidence) AS confidence_avg,
    stddevPopState(confidence) AS confidence_stddev,
    skewPopState(confidence) AS confidence_skew,
    kurtPopState(confidence) AS confidence_kurt
FROM news_agent.news_items
WHERE primary_ccy != ''
GROUP BY hour_bucket, symbol;

-- 4) VIEW: finalize states to readable min/max/avg/stddev/skew/kurtosis per (hour_bucket, symbol).
CREATE VIEW news_agent.hourly_currency_score_stats AS
SELECT
    hour_bucket,
    symbol,
    countMerge(article_count) AS article_count,
    minMerge(bearish_min) AS bearish_min,
    maxMerge(bearish_max) AS bearish_max,
    avgMerge(bearish_avg) AS bearish_avg,
    stddevPopMerge(bearish_stddev) AS bearish_stddev,
    skewPopMerge(bearish_skew) AS bearish_skew,
    kurtPopMerge(bearish_kurt) AS bearish_kurtosis,
    minMerge(bullish_min) AS bullish_min,
    maxMerge(bullish_max) AS bullish_max,
    avgMerge(bullish_avg) AS bullish_avg,
    stddevPopMerge(bullish_stddev) AS bullish_stddev,
    skewPopMerge(bullish_skew) AS bullish_skew,
    kurtPopMerge(bullish_kurt) AS bullish_kurtosis,
    minMerge(neutral_min) AS neutral_min,
    maxMerge(neutral_max) AS neutral_max,
    avgMerge(neutral_avg) AS neutral_avg,
    stddevPopMerge(neutral_stddev) AS neutral_stddev,
    skewPopMerge(neutral_skew) AS neutral_skew,
    kurtPopMerge(neutral_kurt) AS neutral_kurtosis,
    minMerge(timeliness_min) AS timeliness_min,
    maxMerge(timeliness_max) AS timeliness_max,
    avgMerge(timeliness_avg) AS timeliness_avg,
    stddevPopMerge(timeliness_stddev) AS timeliness_stddev,
    skewPopMerge(timeliness_skew) AS timeliness_skew,
    kurtPopMerge(timeliness_kurt) AS timeliness_kurtosis,
    minMerge(volatility_impact_min) AS volatility_impact_min,
    maxMerge(volatility_impact_max) AS volatility_impact_max,
    avgMerge(volatility_impact_avg) AS volatility_impact_avg,
    stddevPopMerge(volatility_impact_stddev) AS volatility_impact_stddev,
    skewPopMerge(volatility_impact_skew) AS volatility_impact_skew,
    kurtPopMerge(volatility_impact_kurt) AS volatility_impact_kurtosis,
    minMerge(confidence_min) AS confidence_min,
    maxMerge(confidence_max) AS confidence_max,
    avgMerge(confidence_avg) AS confidence_avg,
    stddevPopMerge(confidence_stddev) AS confidence_stddev,
    skewPopMerge(confidence_skew) AS confidence_skew,
    kurtPopMerge(confidence_kurt) AS confidence_kurtosis
FROM news_agent.hourly_currency_score_states
GROUP BY hour_bucket, symbol;

-- 5) Backfill from existing news_items (one-time).
INSERT INTO news_agent.hourly_currency_score_states
SELECT
    toStartOfHour(timestamp) AS hour_bucket,
    primary_ccy AS symbol,
    countState() AS article_count,
    minState(bearish_prob) AS bearish_min,
    maxState(bearish_prob) AS bearish_max,
    avgState(bearish_prob) AS bearish_avg,
    stddevPopState(bearish_prob) AS bearish_stddev,
    skewPopState(bearish_prob) AS bearish_skew,
    kurtPopState(bearish_prob) AS bearish_kurt,
    minState(bullish_prob) AS bullish_min,
    maxState(bullish_prob) AS bullish_max,
    avgState(bullish_prob) AS bullish_avg,
    stddevPopState(bullish_prob) AS bullish_stddev,
    skewPopState(bullish_prob) AS bullish_skew,
    kurtPopState(bullish_prob) AS bullish_kurt,
    minState(neutral_prob) AS neutral_min,
    maxState(neutral_prob) AS neutral_max,
    avgState(neutral_prob) AS neutral_avg,
    stddevPopState(neutral_prob) AS neutral_stddev,
    skewPopState(neutral_prob) AS neutral_skew,
    kurtPopState(neutral_prob) AS neutral_kurt,
    minState(timeliness) AS timeliness_min,
    maxState(timeliness) AS timeliness_max,
    avgState(timeliness) AS timeliness_avg,
    stddevPopState(timeliness) AS timeliness_stddev,
    skewPopState(timeliness) AS timeliness_skew,
    kurtPopState(timeliness) AS timeliness_kurt,
    minState(volatility_impact) AS volatility_impact_min,
    maxState(volatility_impact) AS volatility_impact_max,
    avgState(volatility_impact) AS volatility_impact_avg,
    stddevPopState(volatility_impact) AS volatility_impact_stddev,
    skewPopState(volatility_impact) AS volatility_impact_skew,
    kurtPopState(volatility_impact) AS volatility_impact_kurt,
    minState(confidence) AS confidence_min,
    maxState(confidence) AS confidence_max,
    avgState(confidence) AS confidence_avg,
    stddevPopState(confidence) AS confidence_stddev,
    skewPopState(confidence) AS confidence_skew,
    kurtPopState(confidence) AS confidence_kurt
FROM news_agent.news_items
WHERE primary_ccy != ''
GROUP BY hour_bucket, symbol;
