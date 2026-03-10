# Forex Backtesting Library - Quick Start Guide

## Installation

```bash
cd argo_pipelines/forex_backtesting_library

# Install dependencies
pip install -r requirements.txt

# Run tests
python test_setup.py
```

## Run Example

Test the system locally with synthetic data:

```bash
python example_local_run.py
```

This will:
1. Generate synthetic OHLCV data
2. Run trend following strategy with grid search (360 parameter combinations)
3. Save results to JSON
4. Display top 5 performing parameter sets

## Use Real Data

### 1. Set up Oanda (v20 API; practice account, API key only)

```bash
export OANDA_API_KEY=your_api_key
# Default is practice; use --environment live for live
```

### 2. Fetch data

```bash
python scripts/fetch_data.py \
  --symbol USD_JPY \
  --timeframe H1 \
  --start-date 2023-01-01 \
  --output-dir ./data
```

### 3. Run backtest

```bash
python scripts/backtest_strategy.py \
  --symbol USD_JPY \
  --timeframe H1 \
  --strategy trend_following \
  --config config.yaml \
  --data-dir ./data \
  --output-dir ./results
```

Available strategies:
- `trend_following` - Moving average crossover (360 combinations)
- `scalping` - RSI-based (240 combinations)
- `breakout` - Donchian channels (135 combinations)
- `mean_reversion` - Bollinger Bands (396 combinations)

### 4. Store results to ClickHouse

```bash
# Set ClickHouse credentials
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=default
export CLICKHOUSE_PASSWORD=your_password
export CLICKHOUSE_DATABASE=vectorbt_grid

# Store results
python scripts/store_results.py \
  --results-file ./results/USD_JPY_H1_trend_following_*.json
```

## Deploy to Argo Workflows

### 1. Create ConfigMaps

```bash
kubectl create configmap forex-backtesting-config \
  --from-file=config.yaml \
  -n argo-workflows

kubectl create configmap forex-backtesting-scripts \
  --from-file=scripts/ \
  -n argo-workflows
```

### 2. Create Secrets

```bash
kubectl create secret generic forex-backtesting-secrets \
  --from-literal=OANDA_API_KEY=your_key \
  --from-literal=CLICKHOUSE_HOST=your_host \
  --from-literal=CLICKHOUSE_PORT=8123 \
  --from-literal=CLICKHOUSE_USERNAME=default \
  --from-literal=CLICKHOUSE_PASSWORD=your_password \
  -n argo-workflows
```

### 3. Submit Workflow

```bash
argo submit forex_backtesting_workflow.yaml -n argo-workflows

# Watch progress
argo watch @latest -n argo-workflows

# View logs
argo logs @latest -n argo-workflows -f
```

### 4. Customize Parameters

Edit workflow parameters when submitting:

```bash
argo submit forex_backtesting_workflow.yaml \
  -p symbols='["USD_JPY"]' \
  -p timeframes='["H1", "H4"]' \
  -p strategies='["trend_following", "scalping"]' \
  -p start_date="2023-06-01" \
  -n argo-workflows
```

## Query Results

Connect to ClickHouse and query:

```sql
-- Best strategies by Sharpe ratio
SELECT 
    symbol,
    timeframe,
    strategy_type,
    sharpe_ratio,
    total_return,
    max_drawdown,
    params
FROM vectorbt_grid.backtest_grid_results
WHERE sharpe_ratio > 0.5
ORDER BY sharpe_ratio DESC
LIMIT 10;

-- Strategy comparison
SELECT 
    strategy_type,
    COUNT(*) as num_tests,
    AVG(sharpe_ratio) as avg_sharpe,
    MAX(sharpe_ratio) as best_sharpe,
    AVG(total_return) as avg_return
FROM vectorbt_grid.backtest_grid_results
GROUP BY strategy_type
ORDER BY avg_sharpe DESC;
```

## Customize Strategies

Edit `config.yaml` to change grid search parameters:

```yaml
strategies:
  trend_following:
    enabled: true
    fast_window: [10, 20, 30]  # Reduce for faster testing
    slow_window: [50, 100, 150]
    sl_pct: [0.01]
```

## Troubleshooting

### Oanda Connection Issues
- Verify API credentials
- Check account type (practice vs live)
- Ensure instrument names use underscore (USD_JPY not USDJPY)

### Memory Issues
- Reduce grid search ranges in config.yaml
- Process fewer symbols/timeframes in parallel
- Increase container memory limits in Argo workflow

### ClickHouse Connection
- Verify host and port
- Check credentials
- Ensure database is created (script will create automatically)

## Next Steps

1. **Optimize Parameters**: Analyze results to identify best parameter ranges
2. **Walk-Forward**: Implement rolling window backtests
3. **Compare Strategies**: Run all 4 strategies and compare performance
4. **Add Metrics**: Extend with custom metrics (Sortino, Calmar, etc.)
5. **Visualization**: Create dashboards for results analysis

## Support

See full documentation in [README.md](README.md)

For issues, check:
- Test output: `python test_setup.py`
- Logs: `argo logs WORKFLOW_NAME -n argo-workflows`
- ClickHouse: Query `backtest_grid_results` table for execution details
