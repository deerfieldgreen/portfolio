"""
Compute technical features from OHLCV candles.
Features stored as Map(String, Float64) in ClickHouse.
"""
import numpy as np
import pandas as pd
from typing import List, Dict


def compute(candles: List[Dict], pair: str, timeframe: str) -> pd.DataFrame:
    """
    Compute features from raw candles.
    Returns DataFrame with timestamp as index and feature columns.
    """
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["time"])
    df = df.set_index("timestamp").sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # Returns
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["return_21"] = df["close"].pct_change(21)

    # Moving averages
    for window in [5, 10, 21, 50]:
        df[f"sma_{window}"] = df["close"].rolling(window).mean()
        df[f"ema_{window}"] = df["close"].ewm(span=window).mean()

    # Volatility
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_21"] = df["return_1"].rolling(21).std()

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.inf)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / sma20

    # ATR
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Volume features
    df["volume_sma_10"] = df["volume"].rolling(10).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_10"].replace(0, np.inf)

    # Price position
    df["price_vs_sma50"] = (df["close"] - df["sma_50"]) / df["sma_50"]

    # Add metadata
    df["pair"] = pair
    df["timeframe"] = timeframe

    return df.dropna()
