-- ClickHouse schema for VectorBT grid search results
-- Database: {DATABASE} (replaced by setup_database.py from CLICKHOUSE_DATABASE)

-- Table for overall backtest metrics
CREATE TABLE IF NOT EXISTS {DATABASE}.backtests
(
    backtest_id String,
    symbol String,
    timeframe String,
    strategy_type String,
    timestamp DateTime DEFAULT now(),
    initial_capital Float64,
    final_capital Float64,
    total_return Float64,
    sharpe_ratio Float64,
    psr Float64,
    max_drawdown Float64,
    win_rate Float64,
    num_trades UInt32,
    profit_factor Float64,
    avg_trade_duration_hours Float64,
    sortino_ratio Float64,
    calmar_ratio Float64,
    omega_ratio Float64,
    expectancy Float64,
    max_consecutive_wins UInt32,
    max_consecutive_losses UInt32,
    avg_win_pct Float64,
    avg_loss_pct Float64,
    best_trade_pct Float64,
    worst_trade_pct Float64,
    max_drawdown_duration_hours Float64,
    volatility Float64,
    skewness Float64,
    kurtosis Float64,
    tail_ratio Float64,
    recovery_factor Float64,
    params String  -- JSON string of strategy parameters
) ENGINE = MergeTree()
ORDER BY (symbol, strategy_type, timestamp);

-- Table for individual trades
CREATE TABLE IF NOT EXISTS {DATABASE}.backtest_trades
(
    backtest_id String,
    symbol String,
    strategy_type String,
    entry_ts DateTime,
    exit_ts DateTime,
    side String,  -- 'long' or 'short'
    entry_price Float64,
    exit_price Float64,
    size Float64,
    pnl Float64,
    pnl_pct Float64
) ENGINE = MergeTree()
ORDER BY (symbol, entry_ts);

-- Table for grid search results (one row per parameter combination)
CREATE TABLE IF NOT EXISTS {DATABASE}.backtest_grid_results
(
    run_id String,
    symbol String,
    timeframe String,
    strategy_type String,
    timestamp DateTime DEFAULT now(),
    params String,  -- JSON string of all parameters for this grid point
    total_return Float64,
    sharpe_ratio Float64,
    psr Float64,
    max_drawdown Float64,
    win_rate Float64,
    num_trades UInt32,
    profit_factor Float64,
    avg_trade_duration_hours Float64,
    sortino_ratio Float64,
    calmar_ratio Float64,
    omega_ratio Float64,
    expectancy Float64,
    max_consecutive_wins UInt32,
    max_consecutive_losses UInt32,
    avg_win_pct Float64,
    avg_loss_pct Float64,
    best_trade_pct Float64,
    worst_trade_pct Float64,
    max_drawdown_duration_hours Float64,
    volatility Float64,
    skewness Float64,
    kurtosis Float64,
    tail_ratio Float64,
    recovery_factor Float64
) ENGINE = MergeTree()
ORDER BY (symbol, strategy_type, timestamp);

-- Materialized view: auto-filters grid results with sharpe >= 1.0 and num_trades >= 5
CREATE MATERIALIZED VIEW IF NOT EXISTS {DATABASE}.mv_top_sharpe
ENGINE = ReplacingMergeTree()
ORDER BY (symbol, strategy_type, timeframe, run_id)
POPULATE AS
SELECT * FROM {DATABASE}.backtest_grid_results
WHERE sharpe_ratio >= 1.0 AND num_trades >= 5;

-- Materialized view: auto-filters grid results with psr >= 0.5 and num_trades >= 5
CREATE MATERIALIZED VIEW IF NOT EXISTS {DATABASE}.mv_top_psr
ENGINE = ReplacingMergeTree()
ORDER BY (symbol, strategy_type, timeframe, run_id)
POPULATE AS
SELECT * FROM {DATABASE}.backtest_grid_results
WHERE psr >= 0.5 AND num_trades >= 5;
