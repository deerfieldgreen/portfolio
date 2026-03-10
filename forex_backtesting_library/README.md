# Forex Backtesting Library System

A comprehensive modular backtesting system for forex strategies on USDJPY and EURUSD using VectorBT, with data from Oanda starting January 1, 2023, across M30, H1, and H4 timeframes.

## Overview

This system implements a scalable forex backtesting library focused on USDJPY and EURUSD pairs using:
- **VectorBT** for efficient vectorized backtesting with grid search optimization
- **Oanda v20 API** (oandapyV20) for historical OHLCV data from January 1, 2023 (practice account, API key only)
- **ClickHouse** for efficient storage and querying of results
- **Argo Workflows** for parallel execution of modular Python scripts

## Strategy Types

The system supports four strategy types with grid-search parameter tuning:

### 1. Trend Following (MA Crossover)
- Fast MA windows: 5-50
- Slow MA windows: 20-200
- Stop Loss: 0.5%, 1%, 1.5%, 2%
- Timeframes: M30, H1, H4

### 2. Scalping (RSI-based)
- RSI periods: 5-20
- Oversold levels: 20-30
- Overbought levels: 60-80
- Stop Loss: 0.5%, 1%
- Timeframes: M30, H1

### 3. Breakout (Donchian Channels)
- Donchian periods: 10-50
- Stop Loss: 1%, 1.5%, 2%
- Timeframes: H1, H4

### 4. Mean Reversion (Bollinger Bands)
- BB periods: 10-30
- Standard deviations: 1.5-3.0
- Stop Loss: 0.5%, 1%, 1.5%
- Timeframes: H4

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Argo Workflow Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Fetch Data (Parallel per Symbol/Timeframe)         │
│  ├─ USD_JPY × M30, H1, H4                                   │
│  └─ EUR_USD × M30, H1, H4                                   │
│                         ↓                                    │
│  Step 2: Backtest (Parallel per Symbol/TF/Strategy)         │
│  ├─ Trend Following (Grid Search)                           │
│  ├─ Scalping (Grid Search)                                  │
│  ├─ Breakout (Grid Search)                                  │
│  └─ Mean Reversion (Grid Search)                            │
│                         ↓                                    │
│  Step 3: Store Results (Parallel)                           │
│  └─ ClickHouse (vectorbt_grid database)                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
forex_backtesting_library/
├── scripts/
│   ├── fetch_data.py           # Oanda data fetching
│   ├── backtest_strategy.py    # VectorBT backtesting with grid search
│   ├── store_results.py        # ClickHouse result storage
│   └── create_tables.sql       # Database schema
├── config.yaml                 # Strategy parameters and configuration
├── requirements.txt            # Python dependencies
├── forex_backtesting_workflow.yaml  # Argo Workflow definition
└── README.md                   # This file
```

## Setup

### Prerequisites

- Python 3.10+
- Oanda API account and credentials
- ClickHouse instance
- Kubernetes cluster with Argo Workflows (for production)

### Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Oanda (v20 API; practice account, no account ID required):
```bash
export OANDA_API_KEY=your_api_key
# Optional: use live instead of practice
# export OANDA_ENVIRONMENT=live
```

3. Set up ClickHouse connection:
```bash
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=default
export CLICKHOUSE_PASSWORD=your_password
export CLICKHOUSE_DATABASE=vectorbt_grid
```

### Database Setup

Run the SQL schema to create tables:
```bash
clickhouse-client < scripts/create_tables.sql
```

Or the script will automatically create tables on first run.

## Usage

### Local Testing

#### 1. Fetch Data
```bash
python scripts/fetch_data.py \
  --symbol USD_JPY \
  --timeframe H1 \
  --start-date 2023-01-01 \
  --output-dir ./data
```

#### 2. Run Backtest
```bash
python scripts/backtest_strategy.py \
  --symbol USD_JPY \
  --timeframe H1 \
  --strategy trend_following \
  --config config.yaml \
  --data-dir ./data \
  --output-dir ./results
```

#### 3. Store Results
```bash
python scripts/store_results.py \
  --results-file ./results/USD_JPY_H1_trend_following_20240101_120000.json
```

### Argo Workflow Deployment

1. Create ConfigMaps for scripts and config:
```bash
kubectl create configmap forex-backtesting-config \
  --from-file=config.yaml \
  -n argo-workflows

kubectl create configmap forex-backtesting-scripts \
  --from-file=scripts/ \
  -n argo-workflows
```

2. Create Kubernetes secret for credentials:
```bash
kubectl create secret generic forex-backtesting-secrets \
  --from-literal=OANDA_API_KEY=your_key \
  --from-literal=CLICKHOUSE_HOST=your_host \
  --from-literal=CLICKHOUSE_PORT=8123 \
  --from-literal=CLICKHOUSE_USERNAME=default \
  --from-literal=CLICKHOUSE_PASSWORD=your_password \
  -n argo-workflows
```

3. Submit workflow:
```bash
argo submit forex_backtesting_workflow.yaml -n argo-workflows
```

4. Monitor workflow:
```bash
argo watch @latest -n argo-workflows
```

## Configuration

Edit `config.yaml` to customize:
- Symbols and timeframes
- Strategy parameters and grid search ranges
- Risk levels (stop loss percentages)
- Simulation parameters (capital, fees, slippage)

Example configuration structure:
```yaml
data:
  symbols: [USD_JPY, EUR_USD]
  timeframes: [M30, H1, H4]
  start_date: "2023-01-01"

strategies:
  trend_following:
    enabled: true
    fast_window: [5, 10, 15, 20, 25, 30]
    slow_window: [20, 40, 60, 80, 100]
    sl_pct: [0.005, 0.01, 0.015]
```

## Results Storage

Results are stored in ClickHouse `vectorbt_grid` database with three tables:

### 1. `backtests` - Best results per run
- Symbol, timeframe, strategy type
- Performance metrics (return, Sharpe, drawdown, win rate)
- Best parameter combination (JSON)

### 2. `backtest_trades` - Individual trade details
- Entry/exit timestamps and prices
- Trade side (long/short)
- PnL and percentage return

### 3. `backtest_grid_results` - All grid search results
- All parameter combinations tested
- Complete metrics for each combination
- Enables analysis of parameter sensitivity

## Querying Results

Example ClickHouse queries:

```sql
-- Top 10 strategies by Sharpe Ratio
SELECT 
    symbol,
    timeframe,
    strategy_type,
    sharpe_ratio,
    total_return,
    params
FROM vectorbt_grid.backtest_grid_results
ORDER BY sharpe_ratio DESC
LIMIT 10;

-- Best parameters per strategy type
SELECT 
    strategy_type,
    symbol,
    timeframe,
    argMax(params, sharpe_ratio) as best_params,
    max(sharpe_ratio) as best_sharpe
FROM vectorbt_grid.backtest_grid_results
GROUP BY strategy_type, symbol, timeframe;

-- Performance comparison across timeframes
SELECT 
    timeframe,
    strategy_type,
    avg(total_return) as avg_return,
    avg(sharpe_ratio) as avg_sharpe,
    avg(max_drawdown) as avg_drawdown
FROM vectorbt_grid.backtest_grid_results
GROUP BY timeframe, strategy_type
ORDER BY avg_sharpe DESC;
```

## Performance Metrics

The system computes:
- **Total Return**: Overall percentage return
- **Sharpe Ratio**: Risk-adjusted return measure
- **Max Drawdown**: Maximum peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of gross profit to gross loss
- **Average Trade Duration**: Mean holding period

## Extending the System

### Adding New Strategies

1. Add strategy configuration to `config.yaml`
2. Implement strategy function in `backtest_strategy.py`:
```python
def backtest_new_strategy(data, config, initial_capital, fees, slippage):
    # Implement strategy logic with VectorBT
    # Return list of results
    pass
```
3. Update main function to handle new strategy type

### Adding New Metrics

Modify `extract_metrics()` in `backtest_strategy.py` to include additional VectorBT metrics:
```python
sortino_ratio = float(stats.get("Sortino Ratio", 0))
calmar_ratio = float(stats.get("Calmar Ratio", 0))
```

## Best Practices

1. **Start Small**: Test with single symbol/timeframe before full grid
2. **Resource Limits**: Adjust Kubernetes resource requests based on grid size
3. **Data Quality**: Validate Oanda data completeness before backtesting
4. **Overfitting**: Use walk-forward or out-of-sample validation
5. **Transaction Costs**: Include realistic fees and slippage
6. **Storage**: Monitor ClickHouse disk usage with large grids

## Troubleshooting

### Common Issues

1. **Oanda API Rate Limits**: Add delays or use smaller date ranges
2. **Memory Issues**: Reduce grid search ranges or increase container memory
3. **ClickHouse Connection**: Verify credentials and network access
4. **VectorBT Warnings**: Update to latest version or ignore minor warnings

### Logs

View workflow logs:
```bash
argo logs @latest -n argo-workflows
```

View specific step logs:
```bash
argo logs WORKFLOW_NAME -n argo-workflows -c CONTAINER_NAME
```

## Future Enhancements

- RL integration for adaptive parameter selection
- Walk-forward optimization
- Multi-asset portfolio backtesting
- Real-time strategy monitoring
- Web dashboard for results visualization

## References

- [VectorBT Documentation](https://vectorbt.dev/)
- [oandapyV20 (Oanda v20 API)](https://github.com/hootnot/oanda-api-v20)
- [Oanda API Documentation](https://developer.oanda.com/rest-live-v20/introduction/)
- [ClickHouse Documentation](https://clickhouse.com/docs)
- [Argo Workflows](https://argoproj.github.io/workflows/)

## License

MIT License - See repository root for details

## Disclaimer

**Trading Risk Warning**: This software is for educational and research purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always test thoroughly in demo environments and use proper risk management.
