-- news_items: per-article storage; id from uuid5(url). scores JSON + extracted columns for fast filtering.
CREATE TABLE IF NOT EXISTS news_agent.news_items
(
    id               String,
    timestamp        DateTime64(3),
    symbols          Array(String),
    url              String,
    raw_text         String,
    scores           String COMMENT 'Full JSON from LLM',
    summary          String,
    -- Extracted score columns for fast filtering and queries
    relevance_score  Float32 DEFAULT 0,
    volatility_impact Float32 DEFAULT 0,
    timeliness       Float32 DEFAULT 0,
    confidence       Float32 DEFAULT 0,
    primary_ccy      String DEFAULT '' COMMENT 'Extracted for fast filtering',
    bearish_prob     Float32,
    bullish_prob     Float32,
    neutral_prob     Float32
)
ENGINE = ReplacingMergeTree()
ORDER BY (id);

-- Topic 1: Hourly scores by currency. Populated by materialized view on INSERT into news_items.
-- One row per (hour_bucket, symbol) with sum_score and article_count; SummingMergeTree merges multiple inserts per hour.
-- Decay over hours is applied at read time by the API (Topic 2).

CREATE TABLE IF NOT EXISTS news_agent.hourly_currency_scores
(
    hour_bucket   DateTime,
    symbol        String,
    sum_score     Float64,
    article_count UInt64
)
ENGINE = SummingMergeTree()
ORDER BY (hour_bucket, symbol);

-- UNION is not allowed in MATERIALIZED VIEW; use ARRAY JOIN + arrayZip to unpivot currencies.
CREATE MATERIALIZED VIEW IF NOT EXISTS news_agent.mv_hourly_currency_scores
TO news_agent.hourly_currency_scores
AS
SELECT
    toStartOfHour(timestamp) AS hour_bucket,
    t.1 AS symbol,
    sum(t.2) AS sum_score,
    count() AS article_count
FROM news_agent.news_items
ARRAY JOIN arrayZip(
    ['USD', 'EUR', 'JPY', 'GBP'],
    [JSONExtractFloat(scores, 'usd_bias'), JSONExtractFloat(scores, 'eur_bias'), JSONExtractFloat(scores, 'jpy_bias'), JSONExtractFloat(scores, 'gbp_bias')]
) AS t
GROUP BY hour_bucket, symbol;
