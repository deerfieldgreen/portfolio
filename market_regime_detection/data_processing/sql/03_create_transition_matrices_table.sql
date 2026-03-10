-- Create mr_transition_matrices table (prefix mr_ = market_regime)
CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.mr_transition_matrices
(
    timestamp DateTime DEFAULT now(),
    pair String,
    timeframe String,
    n_states UInt8,
    transition_matrix Array(Array(Float32)),  -- 2D array of transition probabilities
    
    -- Metadata
    model_version String DEFAULT 'v1',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, timestamp)
SETTINGS index_granularity = 8192;

-- Create index for latest transition matrix queries
CREATE INDEX IF NOT EXISTS idx_pair_timeframe ON ${CLICKHOUSE_DATABASE}.mr_transition_matrices(pair, timeframe, timestamp) TYPE minmax GRANULARITY 4;
