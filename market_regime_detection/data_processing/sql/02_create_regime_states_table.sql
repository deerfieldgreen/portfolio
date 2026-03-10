-- Create main mr_regime_states table (prefix mr_ = market_regime, project-unique)
CREATE TABLE IF NOT EXISTS ${CLICKHOUSE_DATABASE}.mr_regime_states
(
    -- Identifiers
    timestamp DateTime64(3),
    pair String,
    timeframe String,
    
    -- Core regime outputs
    regime_state UInt8,  -- 0, 1, 2, etc.
    state_prob_0 Float32,
    state_prob_1 Float32,
    state_prob_2 Float32,
    confidence_score Float32,
    
    -- Emission parameters (per state arrays)
    mean_returns_per_state Array(Float32),
    volatility_per_state Array(Float32),
    
    -- Input features
    log_return Float32,
    volatility Float32,
    rsi Float32,
    macd Float32,
    atr Float32,
    
    -- Macroeconomic (FRED daily US-only series)
    policy_rate_us Nullable(Float32),
    interest_rate_2y_us Nullable(Float32),
    interest_rate_10y_us Nullable(Float32),
    dgs30_us Nullable(Float32),
    t10y2y_us Nullable(Float32),
    t10y3m_us Nullable(Float32),
    t10yie_us Nullable(Float32),
    sp500_us Nullable(Float32),
    vixcls_us Nullable(Float32),
    dtwexbgs_us Nullable(Float32),
    usepuindxd_us Nullable(Float32),
    usrecd_us Nullable(Float32),

    -- GARCH(1,1) conditional volatility diagnostic (percentage-scaled units)
    garch_conditional_volatility Nullable(Float32),
    
    -- Model metadata
    n_states UInt8,
    aic Float32,
    bic Float32,
    log_likelihood Float32,
    
    -- Regime metadata
    regime_duration UInt16,
    regime_change UInt8,  -- 1 if regime changed, 0 otherwise
    
    -- Timestamps
    created_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, timestamp)
SETTINGS index_granularity = 8192;

-- Create index on timestamp for faster queries
CREATE INDEX IF NOT EXISTS idx_timestamp ON ${CLICKHOUSE_DATABASE}.mr_regime_states(timestamp) TYPE minmax GRANULARITY 4;

-- Create index on regime_state for filtering
CREATE INDEX IF NOT EXISTS idx_regime_state ON ${CLICKHOUSE_DATABASE}.mr_regime_states(regime_state) TYPE set(0) GRANULARITY 4;
