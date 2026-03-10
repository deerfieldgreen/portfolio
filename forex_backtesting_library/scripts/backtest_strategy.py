#!/usr/bin/env python3
"""
backtest_strategy.py: VectorBT-based backtesting with grid search.
Supports Trend Following, Scalping, Breakout, Mean Reversion, MACD, Stochastic, and ATR Breakout strategies.
"""

import argparse
import json
import logging
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Map Oanda-style timeframe codes to pandas freq strings for VectorBT annualization
TIMEFRAME_TO_FREQ = {
    "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
    "H1": "1h", "H4": "4h",
    "D": "1D", "W": "1W", "M": "1ME",
}

# Hours per bar for avg trade duration (bar count -> hours)
FREQ_HOURS_PER_BAR = {
    "1min": 1 / 60, "5min": 5 / 60, "15min": 0.25, "30min": 0.5,
    "1h": 1, "4h": 4, "1D": 24, "1W": 168, "1ME": 24 * 30,
}

def load_data(symbol: str, timeframe: str, data_dir: str = "/app/data") -> pd.DataFrame:
    """Load OHLCV data from CSV file with validation."""
    filename = f"{symbol}_{timeframe}.csv"
    filepath = Path(data_dir) / filename


    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")


    data = pd.read_csv(filepath, parse_dates=["timestamp"])
    data = data.set_index("timestamp")

    # Validate required columns
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(data.columns)
    if missing:
        raise ValueError(f"Data file {filepath} missing columns: {missing}")

    # Check for NaN/inf in price columns and forward-fill
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        nan_count = int(data[col].isna().sum())
        inf_count = int(np.isinf(data[col]).sum())
        if nan_count > 0 or inf_count > 0:
            logger.warning("Column '%s' has %d NaN and %d inf values in %s — forward-filling", col, nan_count, inf_count, filepath)
            data[col] = data[col].replace([np.inf, -np.inf], np.nan).ffill().bfill()

    # Ensure sorted by timestamp
    if not data.index.is_monotonic_increasing:
        logger.warning("Data in %s is not sorted by timestamp; sorting now", filepath)
        data = data.sort_index()

    # Minimum rows check
    min_rows = 50
    if len(data) < min_rows:
        raise ValueError(f"Insufficient data in {filepath}: {len(data)} rows < minimum {min_rows}")

    logger.info(f"Loaded {len(data)} bars from {filepath}")
    return data


# Required config keys per strategy (used by validate_config)
_STRATEGY_REQUIRED_KEYS = {
    "trend_following": ["ma_type", "fast_window", "slow_window", "sl_pct", "tp_pct"],
    "scalping": ["rsi_period", "oversold", "overbought", "sl_pct", "tp_pct"],
    "breakout": ["donchian_period", "sl_pct", "tp_pct"],
    "mean_reversion": ["bb_period", "bb_std", "sl_pct", "tp_pct"],
    "macd": ["fast_window", "slow_window", "signal_window", "sl_pct", "tp_pct"],
    "stochastic": ["k_period", "d_period", "oversold", "overbought", "sl_pct", "tp_pct"],
    "atr_breakout": ["donchian_period", "atr_window", "atr_multiplier", "sl_pct", "tp_pct"],
}


def validate_config(config: dict, strategy: str) -> None:
    """Validate config has all required keys for the given strategy."""
    if "strategies" not in config:
        raise ValueError("Config missing 'strategies' section")
    if strategy not in config["strategies"]:
        raise ValueError(f"Config missing strategy '{strategy}' in 'strategies' section")

    strategy_config = config["strategies"][strategy]
    required = _STRATEGY_REQUIRED_KEYS.get(strategy, [])
    missing = [k for k in required if k not in strategy_config]
    if missing:
        raise ValueError(f"Strategy '{strategy}' missing required config keys: {missing}")

    for key in required:
        val = strategy_config[key]
        if not isinstance(val, list) or len(val) == 0:
            raise ValueError(f"Strategy '{strategy}' key '{key}' must be a non-empty list, got: {val}")


def _stochastic_kd(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
    """Compute Stochastic %K and %D."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-12)
    k = k.clip(0, 100)
    d = k.rolling(window=d_period).mean()
    return k, d


def _run_one_combo(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_tuple: tuple,
    timeframe: str = "1D",
) -> dict | None:
    """
    Run a single parameter combination for a strategy. Used by workers.
    Returns metrics dict or None on failure.
    """
    try:
        close = data["close"]
        high = data["high"]
        low = data["low"]
        freq = TIMEFRAME_TO_FREQ.get(timeframe, "1D")
        sl_pct = tp_pct = None
        sl_stop = tp_stop = None

        if strategy_name == "trend_following":
            ma_type, fast_w, slow_w, sl_pct, tp_pct = param_tuple
            ewm = ma_type == "ema"
            fast_ma = vbt.MA.run(close, window=fast_w, ewm=ewm, short_name=f"fast_{fast_w}")
            slow_ma = vbt.MA.run(close, window=slow_w, ewm=ewm, short_name=f"slow_{slow_w}")
            entries = fast_ma.ma_crossed_above(slow_ma.ma)
            exits = fast_ma.ma_crossed_below(slow_ma.ma)
            params = {"ma_type": ma_type, "fast_window": int(fast_w), "slow_window": int(slow_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "scalping":
            rsi_period, os_level, ob_level, sl_pct, tp_pct = param_tuple
            rsi = vbt.RSI.run(close, window=rsi_period, short_name=f"rsi_{rsi_period}")
            entries = rsi.rsi_crossed_below(os_level)
            exits = rsi.rsi_crossed_above(ob_level)
            params = {"rsi_period": int(rsi_period), "oversold": int(os_level), "overbought": int(ob_level), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "breakout":
            period, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=period).max()
            lower = low.rolling(window=period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            params = {"donchian_period": int(period), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "mean_reversion":
            period, std, sl_pct, tp_pct = param_tuple
            bb = vbt.BBANDS.run(close, window=period, alpha=std, short_name=f"bb_{period}_{std}")
            entries = close < bb.lower
            exits = close > bb.upper
            params = {"bb_period": int(period), "bb_std": float(std), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "macd":
            fast_w, slow_w, signal_w, sl_pct, tp_pct = param_tuple
            macd = vbt.MACD.run(close, fast_window=fast_w, slow_window=slow_w, signal_window=signal_w)
            entries = macd.macd_crossed_above(macd.signal)
            exits = macd.macd_crossed_below(macd.signal)
            params = {"fast_window": int(fast_w), "slow_window": int(slow_w), "signal_window": int(signal_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "stochastic":
            k_period, d_period, oversold, overbought, sl_pct, tp_pct = param_tuple
            k, d = _stochastic_kd(high, low, close, k_period, d_period)
            entries = (k > d) & (k.shift(1) <= d.shift(1)) & (k.shift(1) < oversold)
            exits = (k < d) & (k.shift(1) >= d.shift(1)) & (k.shift(1) > overbought)
            params = {"k_period": int(k_period), "d_period": int(d_period), "oversold": int(oversold), "overbought": int(overbought), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "atr_breakout":
            donchian_period, atr_window, atr_mult, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=donchian_period).max()
            lower = low.rolling(window=donchian_period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            atr = vbt.ATR.run(high, low, close, window=atr_window).atr
            raw = (atr / close) * atr_mult
            atr_pct = raw.replace([np.inf, -np.inf], np.nan).fillna(sl_pct)
            sl_stop = atr_pct.clip(lower=0.001, upper=0.1)
            tp_stop = tp_pct
            params = {"donchian_period": int(donchian_period), "atr_window": int(atr_window), "atr_multiplier": float(atr_mult), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        else:
            return None

        if sl_stop is None:
            sl_stop = sl_pct
        if tp_stop is None:
            tp_stop = tp_pct

        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            init_cash=initial_capital, fees=fees, slippage=slippage,
            sl_stop=sl_stop, tp_stop=tp_stop,
            freq=freq,
        )
        return extract_metrics(pf, params)
    except Exception as e:
        logger.warning("Strategy %s failed for params %s: %s", strategy_name, param_tuple, e)
        return None


def _run_chunk(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_list: list,
    timeframe: str = "1D",
) -> list:
    """Run a chunk of parameter combinations (one worker). Returns list of metrics dicts."""
    out = []
    for param_tuple in param_list:
        m = _run_one_combo(data, initial_capital, fees, slippage, strategy_name, param_tuple, timeframe)
        if m is not None:
            out.append(m)
    return out


def _run_grid_parallel(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_list: list,
    workers: int,
    timeframe: str = "1D",
) -> list:
    """Run grid in parallel using ProcessPoolExecutor. Each worker gets a chunk of param_list."""
    if not param_list:
        return []
    n = min(workers, len(param_list))
    chunk_size = max(1, (len(param_list) + n - 1) // n)
    chunks = [param_list[i : i + chunk_size] for i in range(0, len(param_list), chunk_size)]
    results = []
    with ProcessPoolExecutor(max_workers=n) as executor:
        futures = {
            executor.submit(_run_chunk, data, initial_capital, fees, slippage, strategy_name, chunk, timeframe): chunk
            for chunk in chunks
        }
        for fut in as_completed(futures):
            results.extend(fut.result())
    return results


def _run_grid(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_list: list,
    workers: int,
    timeframe: str = "1D",
) -> list:
    """Run grid search sequentially or in parallel depending on worker count."""
    if not param_list:
        return []
    if workers is None or workers <= 1:
        return _run_chunk(data, initial_capital, fees, slippage, strategy_name, param_list, timeframe)
    return _run_grid_parallel(data, initial_capital, fees, slippage, strategy_name, param_list, workers, timeframe)


# Required config keys per strategy (used by validate_config)
_STRATEGY_REQUIRED_KEYS = {
    "trend_following": ["ma_type", "fast_window", "slow_window", "sl_pct", "tp_pct"],
    "scalping": ["rsi_period", "oversold", "overbought", "sl_pct", "tp_pct"],
    "breakout": ["donchian_period", "sl_pct", "tp_pct"],
    "mean_reversion": ["bb_period", "bb_std", "sl_pct", "tp_pct"],
    "macd": ["fast_window", "slow_window", "signal_window", "sl_pct", "tp_pct"],
    "stochastic": ["k_period", "d_period", "oversold", "overbought", "sl_pct", "tp_pct"],
    "atr_breakout": ["donchian_period", "atr_window", "atr_multiplier", "sl_pct", "tp_pct"],
}


def validate_config(config: dict, strategy: str) -> None:
    """Validate config has all required keys for the given strategy."""
    if "strategies" not in config:
        raise ValueError("Config missing 'strategies' section")
    if strategy not in config["strategies"]:
        raise ValueError(f"Config missing strategy '{strategy}' in 'strategies' section")

    strategy_config = config["strategies"][strategy]
    required = _STRATEGY_REQUIRED_KEYS.get(strategy, [])
    missing = [k for k in required if k not in strategy_config]
    if missing:
        raise ValueError(f"Strategy '{strategy}' missing required config keys: {missing}")

    for key in required:
        val = strategy_config[key]
        if not isinstance(val, list) or len(val) == 0:
            raise ValueError(f"Strategy '{strategy}' key '{key}' must be a non-empty list, got: {val}")


def _stochastic_kd(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
    """Compute Stochastic %K and %D."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-12)
    k = k.clip(0, 100)
    d = k.rolling(window=d_period).mean()
    return k, d


def _run_one_combo(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_tuple: tuple,
    timeframe: str = "1D",
) -> dict | None:
    """
    Run a single parameter combination for a strategy. Used by workers.
    Returns metrics dict or None on failure.
    """
    try:
        close = data["close"]
        high = data["high"]
        low = data["low"]
        freq = TIMEFRAME_TO_FREQ.get(timeframe, "1D")
        sl_pct = tp_pct = None
        sl_stop = tp_stop = None

        if strategy_name == "trend_following":
            ma_type, fast_w, slow_w, sl_pct, tp_pct = param_tuple
            ewm = ma_type == "ema"
            fast_ma = vbt.MA.run(close, window=fast_w, ewm=ewm, short_name=f"fast_{fast_w}")
            slow_ma = vbt.MA.run(close, window=slow_w, ewm=ewm, short_name=f"slow_{slow_w}")
            entries = fast_ma.ma_crossed_above(slow_ma.ma)
            exits = fast_ma.ma_crossed_below(slow_ma.ma)
            params = {"ma_type": ma_type, "fast_window": int(fast_w), "slow_window": int(slow_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "scalping":
            rsi_period, os_level, ob_level, sl_pct, tp_pct = param_tuple
            rsi = vbt.RSI.run(close, window=rsi_period, short_name=f"rsi_{rsi_period}")
            entries = rsi.rsi_crossed_below(os_level)
            exits = rsi.rsi_crossed_above(ob_level)
            params = {"rsi_period": int(rsi_period), "oversold": int(os_level), "overbought": int(ob_level), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "breakout":
            period, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=period).max()
            lower = low.rolling(window=period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            params = {"donchian_period": int(period), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "mean_reversion":
            period, std, sl_pct, tp_pct = param_tuple
            bb = vbt.BBANDS.run(close, window=period, alpha=std, short_name=f"bb_{period}_{std}")
            entries = close < bb.lower
            exits = close > bb.upper
            params = {"bb_period": int(period), "bb_std": float(std), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "macd":
            fast_w, slow_w, signal_w, sl_pct, tp_pct = param_tuple
            macd = vbt.MACD.run(close, fast_window=fast_w, slow_window=slow_w, signal_window=signal_w)
            entries = macd.macd_crossed_above(macd.signal)
            exits = macd.macd_crossed_below(macd.signal)
            params = {"fast_window": int(fast_w), "slow_window": int(slow_w), "signal_window": int(signal_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "stochastic":
            k_period, d_period, oversold, overbought, sl_pct, tp_pct = param_tuple
            k, d = _stochastic_kd(high, low, close, k_period, d_period)
            entries = (k > d) & (k.shift(1) <= d.shift(1)) & (k.shift(1) < oversold)
            exits = (k < d) & (k.shift(1) >= d.shift(1)) & (k.shift(1) > overbought)
            params = {"k_period": int(k_period), "d_period": int(d_period), "oversold": int(oversold), "overbought": int(overbought), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "atr_breakout":
            donchian_period, atr_window, atr_mult, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=donchian_period).max()
            lower = low.rolling(window=donchian_period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            atr = vbt.ATR.run(high, low, close, window=atr_window).atr
            raw = (atr / close) * atr_mult
            atr_pct = raw.replace([np.inf, -np.inf], np.nan).fillna(sl_pct)
            sl_stop = atr_pct.clip(lower=0.001, upper=0.1)
            tp_stop = tp_pct
            params = {"donchian_period": int(donchian_period), "atr_window": int(atr_window), "atr_multiplier": float(atr_mult), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        else:
            return None

        if sl_stop is None:
            sl_stop = sl_pct
        if tp_stop is None:
            tp_stop = tp_pct

        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            init_cash=initial_capital, fees=fees, slippage=slippage,
            sl_stop=sl_stop, tp_stop=tp_stop,
            freq=freq,
        )
        return extract_metrics(pf, params)
    except Exception as e:
        logger.warning("Strategy %s failed for params %s: %s", strategy_name, param_tuple, e)
        return None


def backtest_trend_following(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest trend following (MA crossover) strategy with grid search."""
    strategy_config = config["strategies"]["trend_following"]
    ma_types = strategy_config["ma_type"]
    fast_windows = strategy_config["fast_window"]
    slow_windows = strategy_config["slow_window"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = [
        (ma_type, fast_w, slow_w, sl_pct, tp_pct)
        for ma_type, fast_w, slow_w, sl_pct, tp_pct in product(
            ma_types, fast_windows, slow_windows, sl_pcts, tp_pcts
        )
        if fast_w < slow_w
    ]
    logger.info("Running Trend Following strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "trend_following", param_list, workers, timeframe)
    logger.info("Completed %d trend following backtests", len(results))
    return results


def backtest_scalping(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest scalping (RSI-based) strategy with grid search."""
    strategy_config = config["strategies"]["scalping"]
    rsi_periods = strategy_config["rsi_period"]
    oversold_levels = strategy_config["oversold"]
    overbought_levels = strategy_config["overbought"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = [
        (rsi_period, os_level, ob_level, sl_pct, tp_pct)
        for rsi_period, os_level, ob_level, sl_pct, tp_pct in product(
            rsi_periods, oversold_levels, overbought_levels, sl_pcts, tp_pcts
        )
        if os_level < ob_level
    ]
    logger.info("Running Scalping strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "scalping", param_list, workers, timeframe)
    logger.info("Completed %d scalping backtests", len(results))
    return results


def backtest_breakout(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest breakout (Donchian channel) strategy with grid search."""
    strategy_config = config["strategies"]["breakout"]
    periods = strategy_config["donchian_period"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = list(product(periods, sl_pcts, tp_pcts))
    logger.info("Running Breakout strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "breakout", param_list, workers, timeframe)
    logger.info("Completed %d breakout backtests", len(results))
    return results


def backtest_mean_reversion(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest mean reversion (Bollinger Bands) strategy with grid search."""
    strategy_config = config["strategies"]["mean_reversion"]
    bb_periods = strategy_config["bb_period"]
    bb_stds = strategy_config["bb_std"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = list(product(bb_periods, bb_stds, sl_pcts, tp_pcts))
    logger.info("Running Mean Reversion strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "mean_reversion", param_list, workers, timeframe)
    logger.info("Completed %d mean reversion backtests", len(results))
    return results


def backtest_macd(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest MACD crossover strategy with grid search."""
    strategy_config = config["strategies"]["macd"]
    fast_windows = strategy_config["fast_window"]
    slow_windows = strategy_config["slow_window"]
    signal_windows = strategy_config["signal_window"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = [
        (fast_w, slow_w, signal_w, sl_pct, tp_pct)
        for fast_w, slow_w, signal_w, sl_pct, tp_pct in product(
            fast_windows, slow_windows, signal_windows, sl_pcts, tp_pcts
        )
        if fast_w < slow_w
    ]
    logger.info("Running MACD strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "macd", param_list, workers, timeframe)
    logger.info("Completed %d MACD backtests", len(results))
    return results


def backtest_stochastic(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest Stochastic oscillator strategy with grid search."""
    strategy_config = config["strategies"]["stochastic"]
    k_periods = strategy_config["k_period"]
    d_periods = strategy_config["d_period"]
    oversold_levels = strategy_config["oversold"]
    overbought_levels = strategy_config["overbought"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = [
        (k_period, d_period, oversold, overbought, sl_pct, tp_pct)
        for k_period, d_period, oversold, overbought, sl_pct, tp_pct in product(
            k_periods, d_periods, oversold_levels, overbought_levels, sl_pcts, tp_pcts
        )
        if oversold < overbought and d_period < k_period
    ]
    logger.info("Running Stochastic strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "stochastic", param_list, workers, timeframe)
    logger.info("Completed %d Stochastic backtests", len(results))
    return results


def backtest_atr_breakout(
    data: pd.DataFrame,
    config: dict,
    initial_capital: float = 100000,
    fees: float = 0.0001,
    slippage: float = 0.0001,
    workers: int = 1,
    timeframe: str = "1D",
) -> list:
    """Backtest Donchian breakout with ATR-based dynamic stop loss."""
    strategy_config = config["strategies"]["atr_breakout"]
    donchian_periods = strategy_config["donchian_period"]
    atr_windows = strategy_config["atr_window"]
    atr_multipliers = strategy_config["atr_multiplier"]
    sl_pcts = strategy_config["sl_pct"]
    tp_pcts = strategy_config["tp_pct"]
    param_list = list(product(donchian_periods, atr_windows, atr_multipliers, sl_pcts, tp_pcts))
    logger.info("Running ATR Breakout strategy (vectorized, %d combos)", len(param_list))
    results = _run_grid(data, initial_capital, fees, slippage, "atr_breakout", param_list, workers, timeframe)
    logger.info("Completed %d ATR Breakout backtests", len(results))
    return results


def extract_trades(pf: vbt.Portfolio) -> list:
    """Extract individual closed trades from a VectorBT portfolio."""
    trades_list = []
    try:
        if not hasattr(pf, "trades") or pf.trades.records is None or len(pf.trades.records) == 0:
            return trades_list
        readable = pf.trades.records_readable
        for _, row in readable.iterrows():
            if str(row.get("Status", "")).lower() != "closed":
                continue
            direction = str(row.get("Direction", "long")).lower()
            side = "long" if "long" in direction else "short"
            trades_list.append({
                "entry_ts": str(row.get("Entry Timestamp", "")),
                "exit_ts": str(row.get("Exit Timestamp", "")),
                "side": side,
                "entry_price": float(row.get("Avg Entry Price", 0)),
                "exit_price": float(row.get("Avg Exit Price", 0)),
                "size": float(row.get("Size", 0)),
                "pnl": float(row.get("PnL", 0)),
                "pnl_pct": float(row.get("Return", 0)),
            })
    except Exception as e:
        logger.warning("Failed to extract trades: %s", e)
    return trades_list


def _compute_avg_trade_duration_hours(pf: vbt.Portfolio, col_idx: int | None, freq: str) -> float:
    """
    Compute average trade duration in hours. VectorBT trades.duration is bar count
    (exit_idx - entry_idx), not time. Convert bars to hours using timeframe.
    """
    try:
        if not hasattr(pf, "trades"):
            return 0.0
        col_name = pf.wrapper.columns[col_idx] if col_idx is not None and pf.wrapper.ndim > 1 else None
        col_trades = pf.trades[col_name] if col_name is not None else pf.trades
        col_trades = col_trades.closed if hasattr(col_trades, "closed") else col_trades
        if col_trades.records is None or len(col_trades.records) == 0:
            return 0.0
        dur = col_trades.duration
        if dur is None or (hasattr(dur, "values") and len(dur.values) == 0):
            return 0.0
        vals = dur.values if hasattr(dur, "values") else np.asarray(dur)
        avg_bars = float(np.mean(vals))
        hours_per_bar = FREQ_HOURS_PER_BAR.get(freq, 24)
        return avg_bars * hours_per_bar
    except Exception:
        return 0.0


def _normal_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (no scipy needed)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_psr(pf: vbt.Portfolio, benchmark_sr: float = 0.0) -> float:
    """Compute Probabilistic Sharpe Ratio (Bailey & Lopez de Prado, 2012).

    PSR(SR*) = Φ((SR - SR*) * √(n-1) / √(1 - γ₃·SR + (γ₄-1)/4 · SR²))

    Returns a probability in [0, 1], or 0.0 on failure.
    """
    try:
        returns = pf.returns()
        if returns is None:
            return 0.0
        r = returns.dropna().values
        n = len(r)
        if n < 3:
            return 0.0
        sr = float(np.mean(r) / np.std(r, ddof=1)) if np.std(r, ddof=1) > 0 else 0.0
        skew = float(np.mean(((r - np.mean(r)) / np.std(r, ddof=1)) ** 3)) if np.std(r, ddof=1) > 0 else 0.0
        excess_kurt = float(np.mean(((r - np.mean(r)) / np.std(r, ddof=1)) ** 4) - 3.0) if np.std(r, ddof=1) > 0 else 0.0
        denom_sq = 1.0 - skew * sr + ((excess_kurt) / 4.0) * sr ** 2
        if denom_sq <= 0:
            return 0.0
        z = (sr - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(denom_sq)
        return _normal_cdf(z)
    except Exception:
        return 0.0


def _safe_float(val, default: float = 0.0, clamp: tuple[float, float] | None = None) -> float:
    """Convert value to float, replacing NaN/Inf with default. Optionally clamp."""
    try:
        v = float(val)
        if not np.isfinite(v):
            return default
        if clamp:
            return min(max(v, clamp[0]), clamp[1])
        return v
    except (TypeError, ValueError):
        return default


def _compute_consecutive_streaks(pf: vbt.Portfolio) -> tuple[int, int]:
    """Compute max consecutive wins and losses from trade records."""
    try:
        if not hasattr(pf, "trades") or pf.trades.records is None or len(pf.trades.records) == 0:
            return 0, 0
        readable = pf.trades.records_readable
        closed = readable[readable["Status"].astype(str).str.lower() == "closed"]
        if closed.empty:
            return 0, 0
        pnls = closed["PnL"].values
        max_wins = max_losses = cur_wins = cur_losses = 0
        for pnl in pnls:
            if pnl > 0:
                cur_wins += 1
                cur_losses = 0
                max_wins = max(max_wins, cur_wins)
            elif pnl < 0:
                cur_losses += 1
                cur_wins = 0
                max_losses = max(max_losses, cur_losses)
            else:
                cur_wins = 0
                cur_losses = 0
        return max_wins, max_losses
    except Exception:
        return 0, 0


def _compute_trade_pct_stats(pf: vbt.Portfolio) -> dict:
    """Compute avg/best/worst trade return percentages."""
    defaults = {"avg_win_pct": 0.0, "avg_loss_pct": 0.0, "best_trade_pct": 0.0, "worst_trade_pct": 0.0}
    try:
        if not hasattr(pf, "trades") or pf.trades.records is None or len(pf.trades.records) == 0:
            return defaults
        readable = pf.trades.records_readable
        closed = readable[readable["Status"].astype(str).str.lower() == "closed"]
        if closed.empty:
            return defaults
        returns = closed["Return"].values
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        return {
            "avg_win_pct": float(np.mean(wins)) if len(wins) > 0 else 0.0,
            "avg_loss_pct": float(np.mean(losses)) if len(losses) > 0 else 0.0,
            "best_trade_pct": float(np.max(returns)) if len(returns) > 0 else 0.0,
            "worst_trade_pct": float(np.min(returns)) if len(returns) > 0 else 0.0,
        }
    except Exception:
        return defaults


def _compute_max_drawdown_duration_hours(pf: vbt.Portfolio, freq: str) -> float:
    """Compute longest drawdown duration in hours."""
    try:
        if not hasattr(pf, "drawdowns"):
            return 0.0
        dd = pf.drawdowns
        if dd.records is None or len(dd.records) == 0:
            return 0.0
        durations = dd.duration.values if hasattr(dd.duration, "values") else np.asarray(dd.duration)
        if len(durations) == 0:
            return 0.0
        max_bars = float(np.max(durations))
        hours_per_bar = FREQ_HOURS_PER_BAR.get(freq, 24)
        return max_bars * hours_per_bar
    except Exception:
        return 0.0


def extract_metrics(pf: vbt.Portfolio, params: dict, include_trades: bool = False, freq: str = "1D") -> dict:
    """Extract performance metrics from portfolio."""
    try:
        stats = pf.stats()
        total_return = float(stats.get("Total Return [%]", 0)) / 100.0
        sharpe_raw = float(stats.get("Sharpe Ratio", 0))
        _SHARPE_MAX, _SHARPE_MIN = 10.0, -10.0
        sharpe_ratio = min(max(sharpe_raw, _SHARPE_MIN), _SHARPE_MAX) if np.isfinite(sharpe_raw) else 0.0
        max_drawdown = float(stats.get("Max Drawdown [%]", 0)) / 100.0
        num_trades = int(stats.get("Total Trades", 0))
        win_rate = float(stats.get("Win Rate [%]", 0)) / 100.0
        profit_factor = float(stats.get("Profit Factor", 0))
        avg_trade_duration = _compute_avg_trade_duration_hours(pf, None, freq)
        psr = compute_psr(pf)

        # Risk-adjusted metrics from pf.stats()
        sortino_ratio = _safe_float(stats.get("Sortino Ratio", 0), clamp=(-10.0, 10.0))
        calmar_ratio = _safe_float(stats.get("Calmar Ratio", 0), clamp=(-10.0, 10.0))
        omega_ratio = _safe_float(stats.get("Omega Ratio", 0), clamp=(-10.0, 100.0))
        expectancy = _safe_float(stats.get("Expectancy", 0))

        # Consecutive streaks
        max_consecutive_wins, max_consecutive_losses = _compute_consecutive_streaks(pf)

        # Trade return stats
        trade_stats = _compute_trade_pct_stats(pf)

        # Max drawdown duration
        max_drawdown_duration_hours = _compute_max_drawdown_duration_hours(pf, freq)

        # Return distribution stats (reuse from PSR computation)
        returns = pf.returns()
        r = returns.dropna().values if returns is not None else np.array([])
        if len(r) > 2 and np.std(r, ddof=1) > 0:
            volatility = float(np.std(r, ddof=1)) * np.sqrt(252)
            z = (r - np.mean(r)) / np.std(r, ddof=1)
            skewness = float(np.mean(z ** 3))
            kurtosis = float(np.mean(z ** 4) - 3.0)
        else:
            volatility = 0.0
            skewness = 0.0
            kurtosis = 0.0

        # Tail ratio: 95th percentile / abs(5th percentile)
        if len(r) > 0:
            p95 = float(np.percentile(r, 95))
            p5 = float(np.percentile(r, 5))
            tail_ratio = p95 / abs(p5) if abs(p5) > 1e-12 else 0.0
        else:
            tail_ratio = 0.0

        # Recovery factor: total return / max drawdown
        abs_dd = abs(max_drawdown)
        recovery_factor = total_return / abs_dd if abs_dd > 1e-12 else 0.0

        result = {
            "params": params,
            "total_return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "psr": psr,
            "max_drawdown": abs_dd,
            "win_rate": win_rate,
            "num_trades": num_trades,
            "profit_factor": _safe_float(profit_factor),
            "avg_trade_duration_hours": avg_trade_duration if avg_trade_duration > 0 else 0,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "omega_ratio": omega_ratio,
            "expectancy": expectancy,
            "max_consecutive_wins": max_consecutive_wins,
            "max_consecutive_losses": max_consecutive_losses,
            "avg_win_pct": trade_stats["avg_win_pct"],
            "avg_loss_pct": trade_stats["avg_loss_pct"],
            "best_trade_pct": trade_stats["best_trade_pct"],
            "worst_trade_pct": trade_stats["worst_trade_pct"],
            "max_drawdown_duration_hours": max_drawdown_duration_hours,
            "volatility": volatility,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "tail_ratio": _safe_float(tail_ratio),
            "recovery_factor": _safe_float(recovery_factor),
        }
        if include_trades:
            result["trades"] = extract_trades(pf)
        return result
    except Exception as e:
        logger.warning("Failed to extract metrics: %s", e)
        out = {
            "params": params,
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "psr": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
            "profit_factor": 0.0,
            "avg_trade_duration_hours": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "omega_ratio": 0.0,
            "expectancy": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "max_drawdown_duration_hours": 0.0,
            "volatility": 0.0,
            "skewness": 0.0,
            "kurtosis": 0.0,
            "tail_ratio": 0.0,
            "recovery_factor": 0.0,
        }
        if include_trades:
            out["trades"] = []
        return out


def _run_one_combo_with_trades(
    data: pd.DataFrame,
    initial_capital: float,
    fees: float,
    slippage: float,
    strategy_name: str,
    param_tuple: tuple,
    timeframe: str = "1D",
) -> dict | None:
    """Re-run a single combo and extract trades. Called only for the best combo."""
    try:
        close = data["close"]
        high = data["high"]
        low = data["low"]
        freq = TIMEFRAME_TO_FREQ.get(timeframe, "1D")
        sl_stop = tp_stop = None

        if strategy_name == "trend_following":
            ma_type, fast_w, slow_w, sl_pct, tp_pct = param_tuple
            ewm = ma_type == "ema"
            fast_ma = vbt.MA.run(close, window=fast_w, ewm=ewm, short_name=f"fast_{fast_w}")
            slow_ma = vbt.MA.run(close, window=slow_w, ewm=ewm, short_name=f"slow_{slow_w}")
            entries = fast_ma.ma_crossed_above(slow_ma.ma)
            exits = fast_ma.ma_crossed_below(slow_ma.ma)
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"ma_type": ma_type, "fast_window": int(fast_w), "slow_window": int(slow_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "scalping":
            rsi_period, os_level, ob_level, sl_pct, tp_pct = param_tuple
            rsi = vbt.RSI.run(close, window=rsi_period, short_name=f"rsi_{rsi_period}")
            entries = rsi.rsi_crossed_below(os_level)
            exits = rsi.rsi_crossed_above(ob_level)
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"rsi_period": int(rsi_period), "oversold": int(os_level), "overbought": int(ob_level), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "breakout":
            period, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=period).max()
            lower = low.rolling(window=period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"donchian_period": int(period), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "mean_reversion":
            period, std, sl_pct, tp_pct = param_tuple
            bb = vbt.BBANDS.run(close, window=period, alpha=std, short_name=f"bb_{period}_{std}")
            entries = close < bb.lower
            exits = close > bb.upper
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"bb_period": int(period), "bb_std": float(std), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "macd":
            fast_w, slow_w, signal_w, sl_pct, tp_pct = param_tuple
            macd = vbt.MACD.run(close, fast_window=fast_w, slow_window=slow_w, signal_window=signal_w)
            entries = macd.macd_crossed_above(macd.signal)
            exits = macd.macd_crossed_below(macd.signal)
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"fast_window": int(fast_w), "slow_window": int(slow_w), "signal_window": int(signal_w), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "stochastic":
            k_period, d_period, oversold, overbought, sl_pct, tp_pct = param_tuple
            k, d = _stochastic_kd(high, low, close, k_period, d_period)
            entries = (k > d) & (k.shift(1) <= d.shift(1)) & (k.shift(1) < oversold)
            exits = (k < d) & (k.shift(1) >= d.shift(1)) & (k.shift(1) > overbought)
            sl_stop, tp_stop = sl_pct, tp_pct
            params = {"k_period": int(k_period), "d_period": int(d_period), "oversold": int(oversold), "overbought": int(overbought), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        elif strategy_name == "atr_breakout":
            donchian_period, atr_window, atr_mult, sl_pct, tp_pct = param_tuple
            upper = high.rolling(window=donchian_period).max()
            lower = low.rolling(window=donchian_period).min()
            entries = close > upper.shift(1)
            exits = close < lower.shift(1)
            atr = vbt.ATR.run(high, low, close, window=atr_window).atr
            raw = (atr / close) * atr_mult
            atr_pct = raw.replace([np.inf, -np.inf], np.nan).fillna(sl_pct)
            sl_stop = atr_pct.clip(lower=0.001, upper=0.1)
            tp_stop = tp_pct
            params = {"donchian_period": int(donchian_period), "atr_window": int(atr_window), "atr_multiplier": float(atr_mult), "sl_pct": float(sl_pct), "tp_pct": float(tp_pct)}
        else:
            return None

        pf = vbt.Portfolio.from_signals(
            close, entries, exits,
            init_cash=initial_capital, fees=fees, slippage=slippage,
            sl_stop=sl_stop, tp_stop=tp_stop,
            freq=freq,
        )
        return extract_metrics(pf, params, include_trades=True)
    except Exception as e:
        logger.warning("Trade extraction failed for %s %s: %s", strategy_name, param_tuple, e)
        return None


def save_results(
    results: list,
    symbol: str,
    timeframe: str,
    strategy_type: str,
    output_dir: str = "/app/results",
    best_trades: list | None = None,
) -> str:
    """Save backtest results to JSON file. Includes trades from best combo."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{timeframe}_{strategy_type}_{run_id}.json"
    filepath = Path(output_dir) / filename


    output_data = {
        "run_id": run_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_type": strategy_type,
        "timestamp": now.isoformat(),
        "num_results": len(results),
        "results": results,
        "best_trades": best_trades or [],
    }

    with open(filepath, "w") as f:
        json.dump(output_data, f, indent=2)
    logger.info("Saved %d results to %s (%d trades)", len(results), filepath, len(best_trades or []))
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Backtest forex strategies with VectorBT")
    parser.add_argument("--symbol", required=True, help="Trading pair (USD_JPY, EUR_USD)")
    parser.add_argument("--timeframe", required=True, help="Timeframe (M30, H1, H4)")
    parser.add_argument("--strategy", required=True,
                        choices=["trend_following", "scalping", "breakout", "mean_reversion", "macd", "stochastic", "atr_breakout"],
                        help="Strategy type")
    parser.add_argument("--config", default="/app/config.yaml", help="Config file path")
    parser.add_argument("--data-dir", default="/app/data", help="Data directory")
    parser.add_argument("--output-dir", default="/app/results", help="Results output directory")
    parser.add_argument("--workers", type=int, default=0,
                        help="Number of parallel workers (0 = use all CPUs, 1 = sequential). Default: 0")
    
    args = parser.parse_args()
    workers = (os.cpu_count() or 1) if args.workers <= 0 else args.workers
    
    try:
        # Load and validate configuration
        with open(args.config) as f:
            config = yaml.safe_load(f)
        validate_config(config, args.strategy)

        # Load data
        data = load_data(args.symbol, args.timeframe, args.data_dir)

        sim_config = config.get("simulation", {})
        initial_capital = sim_config.get("initial_capital", 100000)
        fees = sim_config.get("fees", 0.0001)
        slippage = sim_config.get("slippage", 0.0001)
        # Run backtest based on strategy type (workers: 0 = all CPUs, 1 = sequential)
        if args.strategy == "trend_following":
            results = backtest_trend_following(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "scalping":
            results = backtest_scalping(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "breakout":
            results = backtest_breakout(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "mean_reversion":
            results = backtest_mean_reversion(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "macd":
            results = backtest_macd(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "stochastic":
            results = backtest_stochastic(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        elif args.strategy == "atr_breakout":
            results = backtest_atr_breakout(data, config, initial_capital, fees, slippage, workers=workers, timeframe=args.timeframe)
        else:
            raise ValueError(f"Unknown strategy: {args.strategy}")
        
        # Sort results: prefer combos with trades, then by Sharpe ratio (best first)
        def _sort_key(r):
            has_trades = 1 if r.get("num_trades", 0) > 0 else 0
            return (has_trades, r.get("sharpe_ratio", 0))
        results = sorted(results, key=_sort_key, reverse=True)

        # Re-run best combo with trade extraction
        best_trades = []
        if results:
            best = results[0]
            best_params = best["params"]
            # Reconstruct param_tuple from best_params for _run_one_combo_with_trades
            if args.strategy == "trend_following":
                best_tuple = (best_params["ma_type"], best_params["fast_window"], best_params["slow_window"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "scalping":
                best_tuple = (best_params["rsi_period"], best_params["oversold"], best_params["overbought"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "breakout":
                best_tuple = (best_params["donchian_period"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "mean_reversion":
                best_tuple = (best_params["bb_period"], best_params["bb_std"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "macd":
                best_tuple = (best_params["fast_window"], best_params["slow_window"], best_params["signal_window"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "stochastic":
                best_tuple = (best_params["k_period"], best_params["d_period"], best_params["oversold"], best_params["overbought"], best_params["sl_pct"], best_params["tp_pct"])
            elif args.strategy == "atr_breakout":
                best_tuple = (best_params["donchian_period"], best_params["atr_window"], best_params["atr_multiplier"], best_params["sl_pct"], best_params["tp_pct"])
            else:
                best_tuple = None
            if best_tuple:
                best_with_trades = _run_one_combo_with_trades(data, initial_capital, fees, slippage, args.strategy, best_tuple, args.timeframe)
                if best_with_trades and "trades" in best_with_trades:
                    best_trades = best_with_trades["trades"]
                    if len(best_trades) == 0:
                        logger.warning("Best combo has 0 closed trades (all combos had 0 trades)")
                    else:
                        logger.info("Extracted %d trades from best combo", len(best_trades))

        filepath = save_results(results, args.symbol, args.timeframe, args.strategy, args.output_dir, best_trades=best_trades)

        if results:
            best = results[0]
            logger.info("Best Sharpe Ratio: %.3f with params: %s", best["sharpe_ratio"], best["params"])

        print("SUCCESS:", filepath)
        return 0

    except Exception as e:
        logger.error("Backtest failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
