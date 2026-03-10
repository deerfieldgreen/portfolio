-- Hourly currency scores: from fn_news_items, group by (hour_bucket, primary_ccy).
-- For volatility_impact, timeliness, bearish_prob, bullish_prob, neutral_prob:
--   min, max, mean, stddev, variance (in VIEW), skew, kurtosis,
--   quantiles 1, 5, 25, 50, 75, 95, 99 (in VIEW), range = max - min (in VIEW).
-- article_count = count of articles in the subset (per hour, primary_ccy).
-- Query final stats via VIEW hourly_currency_scores.

-- 1) Drop MVs and VIEWs first, then tables. Drop TABLE hourly_currency_scores before VIEW
-- so the old SummingMergeTree table (same name) is removed; DROP VIEW fails if object is a table.
-- In ClickHouse, materialized views are dropped with DROP VIEW.
DROP VIEW IF EXISTS ${CLICKHOUSE_DATABASE}.mv_hourly_currency_scores;
DROP VIEW IF EXISTS ${CLICKHOUSE_DATABASE}.mv_hourly_currency_score_states;
DROP VIEW IF EXISTS ${CLICKHOUSE_DATABASE}.hourly_currency_score_stats;
DROP TABLE IF EXISTS ${CLICKHOUSE_DATABASE}.hourly_currency_scores;
DROP VIEW IF EXISTS ${CLICKHOUSE_DATABASE}.hourly_currency_scores;
DROP TABLE IF EXISTS ${CLICKHOUSE_DATABASE}.hourly_currency_score_states;

-- 2) Target table: one row per (hour_bucket, symbol) with aggregate states.
-- symbol = primary_ccy from fn_news_items.
CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.hourly_currency_score_states
(
    hour_bucket   DateTime,
    symbol        String,
    article_count AggregateFunction(count, UInt64),
    -- volatility_impact
    volatility_impact_min      AggregateFunction(min, Float32),
    volatility_impact_max      AggregateFunction(max, Float32),
    volatility_impact_mean     AggregateFunction(avg, Float32),
    volatility_impact_stddev   AggregateFunction(stddevPop, Float32),
    volatility_impact_skew    AggregateFunction(skewPop, Float32),
    volatility_impact_kurtosis AggregateFunction(kurtPop, Float32),
    volatility_impact_quantiles AggregateFunction(quantiles(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99), Float32),
    -- timeliness
    timeliness_min      AggregateFunction(min, Float32),
    timeliness_max      AggregateFunction(max, Float32),
    timeliness_mean     AggregateFunction(avg, Float32),
    timeliness_stddev   AggregateFunction(stddevPop, Float32),
    timeliness_skew    AggregateFunction(skewPop, Float32),
    timeliness_kurtosis AggregateFunction(kurtPop, Float32),
    timeliness_quantiles AggregateFunction(quantiles(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99), Float32),
    -- bearish_prob
    bearish_prob_min      AggregateFunction(min, Float32),
    bearish_prob_max      AggregateFunction(max, Float32),
    bearish_prob_mean     AggregateFunction(avg, Float32),
    bearish_prob_stddev   AggregateFunction(stddevPop, Float32),
    bearish_prob_skew    AggregateFunction(skewPop, Float32),
    bearish_prob_kurtosis AggregateFunction(kurtPop, Float32),
    bearish_prob_quantiles AggregateFunction(quantiles(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99), Float32),
    -- bullish_prob
    bullish_prob_min      AggregateFunction(min, Float32),
    bullish_prob_max      AggregateFunction(max, Float32),
    bullish_prob_mean     AggregateFunction(avg, Float32),
    bullish_prob_stddev   AggregateFunction(stddevPop, Float32),
    bullish_prob_skew    AggregateFunction(skewPop, Float32),
    bullish_prob_kurtosis AggregateFunction(kurtPop, Float32),
    bullish_prob_quantiles AggregateFunction(quantiles(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99), Float32),
    -- neutral_prob
    neutral_prob_min      AggregateFunction(min, Float32),
    neutral_prob_max      AggregateFunction(max, Float32),
    neutral_prob_mean     AggregateFunction(avg, Float32),
    neutral_prob_stddev   AggregateFunction(stddevPop, Float32),
    neutral_prob_skew    AggregateFunction(skewPop, Float32),
    neutral_prob_kurtosis AggregateFunction(kurtPop, Float32),
    neutral_prob_quantiles AggregateFunction(quantiles(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99), Float32)
)
ENGINE = AggregatingMergeTree()
ORDER BY (hour_bucket, symbol);

-- 3) MV: on INSERT into fn_news_items, aggregate by (hour_bucket, primary_ccy) and emit states.
CREATE MATERIALIZED VIEW ${CLICKHOUSE_DATABASE}.mv_hourly_currency_scores
TO ${CLICKHOUSE_DATABASE}.hourly_currency_score_states
AS
SELECT
    toStartOfHour(timestamp) AS hour_bucket,
    primary_ccy AS symbol,
    countState() AS article_count,
    minState(volatility_impact) AS volatility_impact_min,
    maxState(volatility_impact) AS volatility_impact_max,
    avgState(volatility_impact) AS volatility_impact_mean,
    stddevPopState(volatility_impact) AS volatility_impact_stddev,
    skewPopState(volatility_impact) AS volatility_impact_skew,
    kurtPopState(volatility_impact) AS volatility_impact_kurtosis,
    quantilesState(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(volatility_impact) AS volatility_impact_quantiles,
    minState(timeliness) AS timeliness_min,
    maxState(timeliness) AS timeliness_max,
    avgState(timeliness) AS timeliness_mean,
    stddevPopState(timeliness) AS timeliness_stddev,
    skewPopState(timeliness) AS timeliness_skew,
    kurtPopState(timeliness) AS timeliness_kurtosis,
    quantilesState(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(timeliness) AS timeliness_quantiles,
    minState(bearish_prob) AS bearish_prob_min,
    maxState(bearish_prob) AS bearish_prob_max,
    avgState(bearish_prob) AS bearish_prob_mean,
    stddevPopState(bearish_prob) AS bearish_prob_stddev,
    skewPopState(bearish_prob) AS bearish_prob_skew,
    kurtPopState(bearish_prob) AS bearish_prob_kurtosis,
    quantilesState(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(bearish_prob) AS bearish_prob_quantiles,
    minState(bullish_prob) AS bullish_prob_min,
    maxState(bullish_prob) AS bullish_prob_max,
    avgState(bullish_prob) AS bullish_prob_mean,
    stddevPopState(bullish_prob) AS bullish_prob_stddev,
    skewPopState(bullish_prob) AS bullish_prob_skew,
    kurtPopState(bullish_prob) AS bullish_prob_kurtosis,
    quantilesState(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(bullish_prob) AS bullish_prob_quantiles,
    minState(neutral_prob) AS neutral_prob_min,
    maxState(neutral_prob) AS neutral_prob_max,
    avgState(neutral_prob) AS neutral_prob_mean,
    stddevPopState(neutral_prob) AS neutral_prob_stddev,
    skewPopState(neutral_prob) AS neutral_prob_skew,
    kurtPopState(neutral_prob) AS neutral_prob_kurtosis,
    quantilesState(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(neutral_prob) AS neutral_prob_quantiles
FROM ${CLICKHOUSE_DATABASE}.fn_news_items
WHERE primary_ccy != ''
GROUP BY hour_bucket, symbol;

-- 4) VIEW: finalize states to readable columns; add variance = stddev^2 and range = max - min per metric.
-- Use table alias 't' so Merge() always receives table columns (AggregateFunction), not SELECT aliases.
CREATE VIEW ${CLICKHOUSE_DATABASE}.hourly_currency_scores AS
SELECT
    t.hour_bucket AS hour_bucket,
    t.symbol AS symbol,
    countMerge(t.article_count) AS article_count,
    -- volatility_impact
    minMerge(t.volatility_impact_min) AS volatility_impact_min,
    maxMerge(t.volatility_impact_max) AS volatility_impact_max,
    maxMerge(t.volatility_impact_max) - minMerge(t.volatility_impact_min) AS volatility_impact_range,
    avgMerge(t.volatility_impact_mean) AS volatility_impact_mean,
    stddevPopMerge(t.volatility_impact_stddev) AS volatility_impact_stddev,
    pow(stddevPopMerge(t.volatility_impact_stddev), 2) AS volatility_impact_variance,
    skewPopMerge(t.volatility_impact_skew) AS volatility_impact_skew,
    kurtPopMerge(t.volatility_impact_kurtosis) AS volatility_impact_kurtosis,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 1) AS volatility_impact_p01,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 2) AS volatility_impact_p05,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 3) AS volatility_impact_p25,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 4) AS volatility_impact_p50,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 5) AS volatility_impact_p75,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 6) AS volatility_impact_p95,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.volatility_impact_quantiles), 7) AS volatility_impact_p99,
    -- timeliness
    minMerge(t.timeliness_min) AS timeliness_min,
    maxMerge(t.timeliness_max) AS timeliness_max,
    maxMerge(t.timeliness_max) - minMerge(t.timeliness_min) AS timeliness_range,
    avgMerge(t.timeliness_mean) AS timeliness_mean,
    stddevPopMerge(t.timeliness_stddev) AS timeliness_stddev,
    pow(stddevPopMerge(t.timeliness_stddev), 2) AS timeliness_variance,
    skewPopMerge(t.timeliness_skew) AS timeliness_skew,
    kurtPopMerge(t.timeliness_kurtosis) AS timeliness_kurtosis,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 1) AS timeliness_p01,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 2) AS timeliness_p05,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 3) AS timeliness_p25,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 4) AS timeliness_p50,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 5) AS timeliness_p75,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 6) AS timeliness_p95,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.timeliness_quantiles), 7) AS timeliness_p99,
    -- bearish_prob
    minMerge(t.bearish_prob_min) AS bearish_prob_min,
    maxMerge(t.bearish_prob_max) AS bearish_prob_max,
    maxMerge(t.bearish_prob_max) - minMerge(t.bearish_prob_min) AS bearish_prob_range,
    avgMerge(t.bearish_prob_mean) AS bearish_prob_mean,
    stddevPopMerge(t.bearish_prob_stddev) AS bearish_prob_stddev,
    pow(stddevPopMerge(t.bearish_prob_stddev), 2) AS bearish_prob_variance,
    skewPopMerge(t.bearish_prob_skew) AS bearish_prob_skew,
    kurtPopMerge(t.bearish_prob_kurtosis) AS bearish_prob_kurtosis,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 1) AS bearish_prob_p01,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 2) AS bearish_prob_p05,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 3) AS bearish_prob_p25,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 4) AS bearish_prob_p50,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 5) AS bearish_prob_p75,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 6) AS bearish_prob_p95,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bearish_prob_quantiles), 7) AS bearish_prob_p99,
    -- bullish_prob
    minMerge(t.bullish_prob_min) AS bullish_prob_min,
    maxMerge(t.bullish_prob_max) AS bullish_prob_max,
    maxMerge(t.bullish_prob_max) - minMerge(t.bullish_prob_min) AS bullish_prob_range,
    avgMerge(t.bullish_prob_mean) AS bullish_prob_mean,
    stddevPopMerge(t.bullish_prob_stddev) AS bullish_prob_stddev,
    pow(stddevPopMerge(t.bullish_prob_stddev), 2) AS bullish_prob_variance,
    skewPopMerge(t.bullish_prob_skew) AS bullish_prob_skew,
    kurtPopMerge(t.bullish_prob_kurtosis) AS bullish_prob_kurtosis,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 1) AS bullish_prob_p01,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 2) AS bullish_prob_p05,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 3) AS bullish_prob_p25,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 4) AS bullish_prob_p50,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 5) AS bullish_prob_p75,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 6) AS bullish_prob_p95,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.bullish_prob_quantiles), 7) AS bullish_prob_p99,
    -- neutral_prob
    minMerge(t.neutral_prob_min) AS neutral_prob_min,
    maxMerge(t.neutral_prob_max) AS neutral_prob_max,
    maxMerge(t.neutral_prob_max) - minMerge(t.neutral_prob_min) AS neutral_prob_range,
    avgMerge(t.neutral_prob_mean) AS neutral_prob_mean,
    stddevPopMerge(t.neutral_prob_stddev) AS neutral_prob_stddev,
    pow(stddevPopMerge(t.neutral_prob_stddev), 2) AS neutral_prob_variance,
    skewPopMerge(t.neutral_prob_skew) AS neutral_prob_skew,
    kurtPopMerge(t.neutral_prob_kurtosis) AS neutral_prob_kurtosis,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 1) AS neutral_prob_p01,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 2) AS neutral_prob_p05,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 3) AS neutral_prob_p25,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 4) AS neutral_prob_p50,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 5) AS neutral_prob_p75,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 6) AS neutral_prob_p95,
    arrayElement(quantilesMerge(0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)(t.neutral_prob_quantiles), 7) AS neutral_prob_p99
FROM ${CLICKHOUSE_DATABASE}.hourly_currency_score_states AS t
GROUP BY t.hour_bucket, t.symbol;
