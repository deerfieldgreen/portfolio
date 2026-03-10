#!/usr/bin/env python3
"""
store_results.py: Store backtest results to ClickHouse.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import clickhouse_connect
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_clickhouse_client():
    """Create ClickHouse client from environment variables."""
    host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    username = os.environ["CLICKHOUSE_USERNAME"]
    password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    database = os.environ.get("CLICKHOUSE_DATABASE", "vectorbt_grid")
    secure = os.environ.get("CLICKHOUSE_SECURE", "false").lower() == "true"
    
    logger.info(f"Connecting to ClickHouse at {host}:{port}, database={database}")
    
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database,
        secure=secure
    )
    
    return client


def _strip_sql_comments(statement: str) -> str:
    """Drop leading full-line comments so CREATE TABLE is not skipped."""
    lines = []
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def ensure_database_and_tables(client, database: str = "vectorbt_grid"):
    """Ensure database and tables exist."""
    # Create database if not exists
    client.command(f"CREATE DATABASE IF NOT EXISTS {database}")
    logger.info(f"Database {database} ensured")
    
    # Read and execute SQL schema
    script_dir = Path(__file__).parent
    sql_file = script_dir / "create_tables.sql"
    
    if sql_file.exists():
        with open(sql_file) as f:
            sql = f.read().replace("{DATABASE}", database)

        for raw in sql.split(";"):
            statement = _strip_sql_comments(raw)
            if not statement or not statement.upper().startswith("CREATE"):
                continue
            try:
                client.command(statement)
                # Log table name: CREATE TABLE IF NOT EXISTS vectorbt_grid.name ...
                parts = statement.split()
                if len(parts) >= 6 and parts[0].upper() == "CREATE":
                    logger.info("Created table: %s", parts[5])
            except Exception as e:
                logger.error("SQL failed: %s", e)
                raise
    else:
        logger.warning(f"SQL schema file not found: {sql_file}")


def store_grid_results(client, results_file: str):
    """Store grid search results to ClickHouse."""
    with open(results_file) as f:
        data = json.load(f)
    
    run_id = data["run_id"]
    symbol = data["symbol"]
    timeframe = data["timeframe"]
    strategy_type = data["strategy_type"]
    timestamp = datetime.fromisoformat(data["timestamp"])
    results = data["results"]
    
    if not results:
        logger.warning("No results to store")
        return 0
    
    # Prepare data for insertion
    rows = []
    for result in results:
        row = {
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy_type": strategy_type,
            "timestamp": timestamp,
            "params": json.dumps(result["params"]),
            "total_return": result["total_return"],
            "sharpe_ratio": result["sharpe_ratio"],
            "psr": result.get("psr", 0.0),
            "max_drawdown": result["max_drawdown"],
            "win_rate": result["win_rate"],
            "num_trades": result["num_trades"],
            "profit_factor": result.get("profit_factor", 0.0),
            "avg_trade_duration_hours": result.get("avg_trade_duration_hours", 0.0),
            "sortino_ratio": result.get("sortino_ratio", 0.0),
            "calmar_ratio": result.get("calmar_ratio", 0.0),
            "omega_ratio": result.get("omega_ratio", 0.0),
            "expectancy": result.get("expectancy", 0.0),
            "max_consecutive_wins": result.get("max_consecutive_wins", 0),
            "max_consecutive_losses": result.get("max_consecutive_losses", 0),
            "avg_win_pct": result.get("avg_win_pct", 0.0),
            "avg_loss_pct": result.get("avg_loss_pct", 0.0),
            "best_trade_pct": result.get("best_trade_pct", 0.0),
            "worst_trade_pct": result.get("worst_trade_pct", 0.0),
            "max_drawdown_duration_hours": result.get("max_drawdown_duration_hours", 0.0),
            "volatility": result.get("volatility", 0.0),
            "skewness": result.get("skewness", 0.0),
            "kurtosis": result.get("kurtosis", 0.0),
            "tail_ratio": result.get("tail_ratio", 0.0),
            "recovery_factor": result.get("recovery_factor", 0.0),
        }
        rows.append(row)
    
    # Insert into ClickHouse
    df = pd.DataFrame(rows)
    table = "backtest_grid_results"
    
    client.insert_df(table, df)
    logger.info(f"Inserted {len(rows)} rows into {table}")
    
    return len(rows)


def store_trades(client, results_file: str):
    """Store individual trades from the best combo into backtest_trades."""
    with open(results_file) as f:
        data = json.load(f)

    trades = data.get("best_trades", [])
    if not trades:
        logger.info("No trades to store (best_trades empty or missing)")
        return 0

    run_id = data["run_id"]
    symbol = data["symbol"]
    strategy_type = data["strategy_type"]

    rows = []
    for t in trades:
        rows.append({
            "backtest_id": run_id,
            "symbol": symbol,
            "strategy_type": strategy_type,
            "entry_ts": datetime.fromisoformat(t["entry_ts"].replace("Z", "+00:00")) if t.get("entry_ts") else datetime.now(),
            "exit_ts": datetime.fromisoformat(t["exit_ts"].replace("Z", "+00:00")) if t.get("exit_ts") else datetime.now(),
            "side": t.get("side", "long"),
            "entry_price": float(t.get("entry_price", 0)),
            "exit_price": float(t.get("exit_price", 0)),
            "size": float(t.get("size", 0)),
            "pnl": float(t.get("pnl", 0)),
            "pnl_pct": float(t.get("pnl_pct", 0)),
        })

    df = pd.DataFrame(rows)
    client.insert_df("backtest_trades", df)
    logger.info("Inserted %d trades into backtest_trades", len(rows))
    return len(rows)


def store_best_backtest(client, results_file: str):
    """Store the best performing backtest to the backtests table."""
    with open(results_file) as f:
        data = json.load(f)
    
    results = data["results"]
    
    if not results:
        logger.warning("No results to store")
        return
    
    # Find best result by Sharpe ratio
    best = max(results, key=lambda x: x.get("sharpe_ratio", -999))
    
    run_id = data["run_id"]
    symbol = data["symbol"]
    timeframe = data["timeframe"]
    strategy_type = data["strategy_type"]
    timestamp = datetime.fromisoformat(data["timestamp"])
    
    # Assume initial capital from config (default 100000)
    initial_capital = 100000.0
    final_capital = initial_capital * (1 + best["total_return"])
    
    row = {
        "backtest_id": run_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_type": strategy_type,
        "timestamp": timestamp,
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return": best["total_return"],
        "sharpe_ratio": best["sharpe_ratio"],
        "psr": best.get("psr", 0.0),
        "max_drawdown": best["max_drawdown"],
        "win_rate": best["win_rate"],
        "num_trades": best["num_trades"],
        "profit_factor": best.get("profit_factor", 0.0),
        "avg_trade_duration_hours": best.get("avg_trade_duration_hours", 0.0),
        "sortino_ratio": best.get("sortino_ratio", 0.0),
        "calmar_ratio": best.get("calmar_ratio", 0.0),
        "omega_ratio": best.get("omega_ratio", 0.0),
        "expectancy": best.get("expectancy", 0.0),
        "max_consecutive_wins": best.get("max_consecutive_wins", 0),
        "max_consecutive_losses": best.get("max_consecutive_losses", 0),
        "avg_win_pct": best.get("avg_win_pct", 0.0),
        "avg_loss_pct": best.get("avg_loss_pct", 0.0),
        "best_trade_pct": best.get("best_trade_pct", 0.0),
        "worst_trade_pct": best.get("worst_trade_pct", 0.0),
        "max_drawdown_duration_hours": best.get("max_drawdown_duration_hours", 0.0),
        "volatility": best.get("volatility", 0.0),
        "skewness": best.get("skewness", 0.0),
        "kurtosis": best.get("kurtosis", 0.0),
        "tail_ratio": best.get("tail_ratio", 0.0),
        "recovery_factor": best.get("recovery_factor", 0.0),
        "params": json.dumps(best["params"]),
    }
    
    df = pd.DataFrame([row])
    table = "backtests"
    
    client.insert_df(table, df)
    logger.info(f"Inserted best result into {table}: Sharpe={best['sharpe_ratio']:.3f}")


def main():
    parser = argparse.ArgumentParser(description="Store backtest results to ClickHouse")
    parser.add_argument("--results-file", required=True, help="Path to results JSON file")
    parser.add_argument("--store-grid", action="store_true", help="Store all grid results")
    parser.add_argument("--store-best", action="store_true", help="Store best result only")
    
    args = parser.parse_args()
    
    try:
        client = get_clickhouse_client()
        database = os.environ.get("CLICKHOUSE_DATABASE", "vectorbt_grid")
        
        # Ensure database and tables exist
        ensure_database_and_tables(client, database)
        
        # Store results
        stored_count = 0
        
        if args.store_grid:
            stored_count += store_grid_results(client, args.results_file)
        
        if args.store_best:
            store_best_backtest(client, args.results_file)
            stored_count += 1
        
        if not args.store_grid and not args.store_best:
            # Default: store all three
            stored_count += store_grid_results(client, args.results_file)
            store_best_backtest(client, args.results_file)
            stored_count += store_trades(client, args.results_file)
        
        logger.info(f"Successfully stored results from {args.results_file}")
        print(f"SUCCESS: Stored {stored_count} records")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to store results: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
