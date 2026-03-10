-- k8s/clickhouse-tables.sql
-- All tables live in cervid_analytics with fxs_ prefix
-- Every statement is idempotent (IF NOT EXISTS / INSERT ... SELECT ... WHERE NOT EXISTS)

-- ============================================================
-- SERVING UNIVERSE: human-defined pair/TF combos to serve
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_serving_universe (
    pair             LowCardinality(String),
    timeframe        LowCardinality(String),
    oanda_instrument String,
    active           UInt8 DEFAULT 1,
    candle_count     UInt32 DEFAULT 500,
    inserted_at      DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (pair, timeframe);

-- Seed initial universe (G10 majors, H1 + H4) — only if empty
INSERT INTO fxs_serving_universe (pair, timeframe, oanda_instrument)
SELECT pair, timeframe, oanda_instrument
FROM (
    SELECT 'USD_JPY' AS pair, 'H1' AS timeframe, 'USD_JPY' AS oanda_instrument
    UNION ALL SELECT 'USD_JPY', 'H4', 'USD_JPY'
    UNION ALL SELECT 'EUR_USD', 'H1', 'EUR_USD'
    UNION ALL SELECT 'EUR_USD', 'H4', 'EUR_USD'
    UNION ALL SELECT 'GBP_USD', 'H1', 'GBP_USD'
    UNION ALL SELECT 'GBP_USD', 'H4', 'GBP_USD'
    UNION ALL SELECT 'AUD_USD', 'H1', 'AUD_USD'
    UNION ALL SELECT 'AUD_USD', 'H4', 'AUD_USD'
    UNION ALL SELECT 'USD_CHF', 'H1', 'USD_CHF'
    UNION ALL SELECT 'USD_CHF', 'H4', 'USD_CHF'
    UNION ALL SELECT 'USD_CAD', 'H1', 'USD_CAD'
    UNION ALL SELECT 'USD_CAD', 'H4', 'USD_CAD'
    UNION ALL SELECT 'NZD_USD', 'H1', 'NZD_USD'
    UNION ALL SELECT 'NZD_USD', 'H4', 'NZD_USD'
) seeds
WHERE (SELECT count() FROM fxs_serving_universe) = 0;


-- ============================================================
-- INSTRUMENT FEATURES: OHLCV + computed features
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_instrument_features (
    pair             LowCardinality(String),
    timeframe        LowCardinality(String),
    timestamp        DateTime64(3),
    open             Float64,
    high             Float64,
    low              Float64,
    close            Float64,
    volume           Float64,
    features         Map(String, Float64),
    inserted_at      DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (pair, timeframe, timestamp);


-- ============================================================
-- PREDICTIONS: model predictions (backfilled with actuals)
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_predictions (
    pair              LowCardinality(String),
    timeframe         LowCardinality(String),
    timestamp         DateTime64(3),
    model_registry    String,
    model_version     String,
    architecture      LowCardinality(String),
    pred_next_close   Float64,
    actual_close      Nullable(Float64),
    error_pips        Nullable(Float64),
    inserted_at       DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (pair, timeframe, timestamp, model_registry);


-- ============================================================
-- CROSS-TF SNAPSHOT
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_cross_tf_snapshot (
    pair              LowCardinality(String),
    snapshot_ts       DateTime64(3),
    data              Map(String, Float64),
    trend_aligned     UInt8,
    inserted_at       DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (pair, snapshot_ts);


-- ============================================================
-- EXPERIMENTS: swarm experiment log (analytical backbone)
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_experiments (
    run_id            String,
    experiment_id     String,
    parent_run_ids    Array(String),
    timestamp         DateTime64(3),
    architecture      LowCardinality(String),
    model_family      LowCardinality(String),
    hyperparameters   Map(String, String),
    feature_set       Array(String),
    strategy_type     String,
    strategy_description String,
    research_references Array(String),
    pair              LowCardinality(String),
    timeframe         LowCardinality(String),
    sequence_length   UInt32,
    epochs_trained    UInt32,
    train_samples     UInt64,
    val_samples       UInt64,
    test_samples      UInt64,
    training_time_sec Float64,
    gpu_type          LowCardinality(String),
    metrics           Map(String, Float64),
    train_val_gap     Float64,
    directional_accuracy Float64,
    profit_factor     Nullable(Float64),
    deflated_sharpe   Nullable(Float64),
    pbo               Nullable(Float64),
    estimated_cost_usd Float64,
    llm_tokens_used   UInt64,
    status            LowCardinality(String),
    failure_detail    Nullable(String),
    strategist_reasoning String,
    novelty_score     Float64,
    predicted_sharpe  Nullable(Float64),
    swarm_cycle       UInt32,
    research_direction LowCardinality(String),
    bandit_arm        LowCardinality(String),
    inserted_at       DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (pair, timeframe, architecture, timestamp, run_id);


-- ============================================================
-- INSIGHTS: ExpeL-style extracted rules
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_insights (
    insight_id        String,
    text              String,
    source_run_ids    Array(String),
    created_at        DateTime64(3),
    updated_at        DateTime64(3),
    status            LowCardinality(String),
    confidence        Float64,
    category          LowCardinality(String),
    inserted_at       DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (category, insight_id);


-- ============================================================
-- RESEARCH SOURCES: human-curated list of sites + arXiv categories
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_research_sources (
    source_id         String,
    source_type       LowCardinality(String),
    arxiv_category    Nullable(String),
    arxiv_keywords    Array(String),
    site_domain       Nullable(String),
    site_search_terms Array(String),
    description       String,
    priority          UInt8 DEFAULT 5,
    max_items_per_crawl UInt8 DEFAULT 5,
    active            UInt8 DEFAULT 1,
    inserted_at       DateTime64(3) DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(inserted_at)
ORDER BY (source_type, source_id);


-- ============================================================
-- RESEARCH CRAWL LOG: xxhash dedup
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_research_crawl_log (
    content_hash      UInt64,
    url               String,
    title             String,
    source_id         String,
    crawled_at        DateTime64(3) DEFAULT now64(3),
    relevant          UInt8,
    relevance_score   Float64,
    entry_id          Nullable(String),
    chunks_created    UInt16 DEFAULT 0
) ENGINE = ReplacingMergeTree(crawled_at)
ORDER BY (content_hash);


-- ============================================================
-- RESEARCH CORPUS: embedded chunks of accepted research
-- ============================================================
CREATE TABLE IF NOT EXISTS fxs_research_corpus (
    entry_id          String,
    source_type       LowCardinality(String),
    source_id         Nullable(String),
    title             String,
    authors           Array(String),
    url               Nullable(String),
    year              UInt16,
    chunk_index       UInt16,
    chunk_text        String,
    topics            Array(String),
    asset_classes     Array(String),
    strategy_families Array(String),
    model_families    Array(String),
    relevance_score   Float64 DEFAULT 1.0,
    ingested_at       DateTime64(3) DEFAULT now64(3),
    status            LowCardinality(String) DEFAULT 'active'
) ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (entry_id, chunk_index);


-- ============================================================
-- SEED: research_sources (only if table is empty)
-- ============================================================

-- arXiv categories
INSERT INTO fxs_research_sources
    (source_id, source_type, arxiv_category, arxiv_keywords, description, priority, max_items_per_crawl)
SELECT source_id, source_type, arxiv_category, arxiv_keywords, description, priority, max_items_per_crawl
FROM (
    SELECT generateUUIDv4() AS source_id, 'arxiv_category' AS source_type, 'q-fin.TR' AS arxiv_category,
     ['forex', 'exchange rate', 'currency', 'FX', 'trading strategy', 'execution'] AS arxiv_keywords,
     'Trading and Market Microstructure' AS description, toUInt8(1) AS priority, toUInt8(5) AS max_items_per_crawl
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'q-fin.ST',
     ['regime', 'volatility', 'cointegration', 'time series', 'stochastic'],
     'Statistical Finance', 2, 5
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'q-fin.CP',
     ['neural network', 'deep learning', 'machine learning', 'reinforcement learning', 'prediction'],
     'Computational Finance', 2, 5
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'q-fin.PM',
     ['portfolio', 'allocation', 'risk', 'currency', 'hedging'],
     'Portfolio Management', 4, 3
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'cs.LG',
     ['time series forecasting', 'financial', 'exchange rate', 'temporal convolution', 'state space model'],
     'Machine Learning', 5, 3
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'stat.ML',
     ['time series', 'sequential', 'financial', 'forecasting', 'bayesian'],
     'Statistical ML', 5, 2
    UNION ALL SELECT generateUUIDv4(), 'arxiv_category', 'eess.SP',
     ['financial signal', 'wavelet', 'denoising', 'decomposition', 'frequency'],
     'Signal Processing', 6, 2
) seeds
WHERE (SELECT count() FROM fxs_research_sources WHERE source_type = 'arxiv_category') = 0;

-- Curated sites via Tavily
INSERT INTO fxs_research_sources
    (source_id, source_type, site_domain, site_search_terms, description, priority, max_items_per_crawl)
SELECT source_id, source_type, site_domain, site_search_terms, description, priority, max_items_per_crawl
FROM (
    SELECT generateUUIDv4() AS source_id, 'tavily_site' AS source_type, 'quantpedia.com' AS site_domain,
     ['forex strategy', 'currency momentum', 'FX carry trade', 'mean reversion forex'] AS site_search_terms,
     'Quantpedia' AS description, toUInt8(1) AS priority, toUInt8(3) AS max_items_per_crawl
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'papers.ssrn.com',
     ['forex machine learning', 'currency prediction deep learning', 'FX regime switching'],
     'SSRN', 2, 3
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'paperswithcode.com',
     ['time series forecasting benchmark', 'exchange rate prediction', 'Mamba time series'],
     'Papers With Code', 3, 2
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'risk.net',
     ['FX prediction', 'currency risk', 'quant trading forex', 'machine learning FX'],
     'Risk.net', 4, 2
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'hudsonthames.org',
     ['pairs trading', 'statistical arbitrage', 'cointegration', 'mean reversion'],
     'Hudson and Thames', 4, 2
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'blog.ml4trading.io',
     ['forex feature engineering', 'time series deep learning trading'],
     'ML4Trading', 5, 2
    UNION ALL SELECT generateUUIDv4(), 'tavily_site', 'alpaca.markets',
     ['forex algorithm', 'currency trading ML', 'FX strategy backtest'],
     'Alpaca community research', 6, 1
) seeds
WHERE (SELECT count() FROM fxs_research_sources WHERE source_type = 'tavily_site') = 0;
