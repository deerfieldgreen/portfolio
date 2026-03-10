-- fn_news_items: per-article storage, id from uuid5(url). scores JSON + extracted columns for fast filtering.
-- Prefix fn_ = financial_news (project-unique). Database from env: CLICKHOUSE_DATABASE.
CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.fn_news_items
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
