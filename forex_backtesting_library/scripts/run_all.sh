#!/usr/bin/env bash
# run_all.sh: Fetch data, backtest all strategies, and store results.
# Run from the forex_backtesting_library directory.
# Requires: OANDA_API_KEY, CLICKHOUSE_USERNAME, CLICKHOUSE_PASSWORD set.
set -euo pipefail

SYMBOLS=(USD_JPY EUR_USD)
TIMEFRAMES=(M30 H1 H4)
STRATEGIES=(trend_following scalping breakout mean_reversion macd stochastic atr_breakout)
START_DATE="2023-01-01"
DATA_DIR="./data"
RESULTS_DIR="./results"
CONFIG="config.yaml"

echo "=== Step 1: Fetch data ==="
for symbol in "${SYMBOLS[@]}"; do
  for tf in "${TIMEFRAMES[@]}"; do
    csv="${DATA_DIR}/${symbol}_${tf}.csv"
    if [ -f "$csv" ]; then
      echo "SKIP: $csv already exists"
    else
      echo "FETCH: $symbol $tf"
      python scripts/fetch_data.py --symbol "$symbol" --timeframe "$tf" --start-date "$START_DATE" --output-dir "$DATA_DIR"
    fi
  done
done

echo ""
echo "=== Step 2: Backtest all combinations ==="
for symbol in "${SYMBOLS[@]}"; do
  for tf in "${TIMEFRAMES[@]}"; do
    for strategy in "${STRATEGIES[@]}"; do
      echo "BACKTEST: $symbol $tf $strategy"
      python scripts/backtest_strategy.py \
        --symbol "$symbol" --timeframe "$tf" --strategy "$strategy" \
        --config "$CONFIG" --data-dir "$DATA_DIR" --output-dir "$RESULTS_DIR" \
        --workers 1
    done
  done
done

echo ""
echo "=== Step 3: Store all results ==="
for file in "$RESULTS_DIR"/*.json; do
  echo "STORE: $file"
  python scripts/store_results.py --results-file "$file"
done

echo ""
echo "=== Done ==="
echo "Total JSON files: $(ls -1 "$RESULTS_DIR"/*.json 2>/dev/null | wc -l)"
