-- Migration: add extracted score columns to existing news_items tables.
-- Run this if news_items was created before the schema update.
-- Each ADD COLUMN is idempotent in ClickHouse 24+ (IF NOT EXISTS); older versions may error if column exists.

ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS relevance_score Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS volatility_impact Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS timeliness Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS confidence Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS primary_ccy String DEFAULT '';
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS bearish_prob Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS bullish_prob Float32 DEFAULT 0;
ALTER TABLE news_agent.news_items ADD COLUMN IF NOT EXISTS neutral_prob Float32 DEFAULT 0;
