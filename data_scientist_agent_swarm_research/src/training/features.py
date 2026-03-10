"""
Feature computation utilities shared between serving and training images.
Kept minimal since src/shared/ changes trigger ALL image rebuilds.
"""
import numpy as np
import pandas as pd


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute return features."""
    for period in [1, 5, 10, 21]:
        df[f"return_{period}"] = df["close"].pct_change(period)
    return df


def compute_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Compute SMA and EMA features."""
    for window in [5, 10, 21, 50]:
        df[f"sma_{window}"] = df["close"].rolling(window).mean()
        df[f"ema_{window}"] = df["close"].ewm(span=window).mean()
    return df


def compute_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """Compute volatility features."""
    if "return_1" not in df.columns:
        df["return_1"] = df["close"].pct_change()
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_21"] = df["return_1"].rolling(21).std()
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute RSI."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.inf)
    df[f"rsi_{period}"] = 100 - (100 / (1 + rs))
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute ATR."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[f"atr_{period}"] = tr.rolling(period).mean()
    return df


def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all feature computations."""
    df = compute_returns(df)
    df = compute_moving_averages(df)
    df = compute_volatility(df)
    df = compute_rsi(df)
    df = compute_atr(df)
    return df
