"""
Data processing module for market regime detection.
Fetches forex data, computes features (log returns, volatility, technical indicators),
and optionally integrates macroeconomic differentials.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[str] = None) -> Dict:
    """Load configuration from YAML file. Tries config.yaml (container) then ../config.yaml (local)."""
    base = Path(__file__).parent
    candidates = (config_path,) if config_path else ("config.yaml", "../config.yaml")
    config_file = None
    for c in candidates:
        p = (base / c).resolve()
        if p.exists():
            config_file = p
            break
    if config_file is None:
        config_file = base / (config_path or "config.yaml")
    if not config_file.exists():
        config_yaml = os.environ.get("CONFIG_YAML", "")
        if config_yaml:
            return yaml.safe_load(config_yaml)
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def fetch_oanda_data(
    pair: str,
    timeframe: str,
    lookback_days: int,
    api_key: Optional[str] = None
) -> pd.DataFrame:
    """
    Fetch OHLCV data from OANDA API.
    
    Args:
        pair: Currency pair (e.g., "USD_JPY")
        timeframe: Timeframe (e.g., "H1", "H4", "D")
        lookback_days: Number of days of historical data
        api_key: OANDA API key (from env if not provided)
    
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    try:
        from oandapyV20 import API
        from oandapyV20.contrib.factories import InstrumentsCandlesFactory
    except ImportError:
        logger.warning("oandapyV20 not available")
        raise ValueError("oandapyV20 required for OANDA data. Install: pip install oandapyV20")
    
    if api_key is None:
        api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        raise ValueError("OANDA_API_KEY required. Set env var or pass api_key.")
    
    granularity_map = {"H1": "H1", "H4": "H4", "D": "D"}
    granularity = granularity_map.get(timeframe, "H1")
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)
    from_param = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_param = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    instrument = pair.replace("/", "_")
    environment = os.environ.get("OANDA_ENVIRONMENT", "practice")
    client = API(access_token=api_key, environment=environment)
    params = {"from": from_param, "to": to_param, "granularity": granularity, "price": "M"}
    
    data = []
    try:
        def _do_fetch():
            _data = []
            for request in InstrumentsCandlesFactory(instrument=instrument, params=params):
                client.request(request)
                for candle in request.response.get("candles", []):
                    if not candle.get("complete", True):
                        continue
                    mid = candle.get("mid") or {}
                    _data.append({
                        "timestamp": pd.to_datetime(candle["time"]),
                        "open": float(mid["o"]),
                        "high": float(mid["h"]),
                        "low": float(mid["l"]),
                        "close": float(mid["c"]),
                        "volume": int(candle.get("volume", 0))
                    })
            return _data

        data = _retry(_do_fetch)
        if not data:
            raise ValueError(f"No candles returned for {pair} {timeframe}")
        df = pd.DataFrame(data)
        logger.info(f"Fetched {len(df)} candles for {pair} from OANDA")
        return df
    except Exception as e:
        logger.error(f"Error fetching OANDA data: {e}")
        raise


def compute_features(df: pd.DataFrame, config: Dict) -> pd.DataFrame:
    """
    Compute features for regime detection.
    
    Args:
        df: DataFrame with OHLCV data
        config: Configuration dictionary
    
    Returns:
        DataFrame with additional feature columns
    """
    df = df.copy()
    feature_config = config.get("features", {})
    
    # Log returns
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    
    # Rolling volatility (standard deviation of returns)
    vol_window = feature_config.get("volatility_window", 20)
    df["volatility"] = df["log_return"].rolling(window=vol_window).std()
    
    # RSI (Relative Strength Index)
    rsi_window = feature_config.get("rsi_window", 14)
    df["rsi"] = compute_rsi(df["close"], period=rsi_window)
    
    # MACD
    fast = feature_config.get("macd_fast", 12)
    slow = feature_config.get("macd_slow", 26)
    signal = feature_config.get("macd_signal", 9)
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(
        df["close"], fast_period=fast, slow_period=slow, signal_period=signal
    )
    
    # ATR (Average True Range)
    atr_window = feature_config.get("atr_window", 14)
    df["atr"] = compute_atr(df, period=atr_window)
    
    # Drop NaN rows created by rolling windows
    df = df.dropna()
    if df.empty:
        raise ValueError("DataFrame is empty after dropping NaN rows. Not enough data for feature computation.")

    logger.info(f"Computed features, shape: {df.shape}")
    return df


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.finfo(float).eps)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    prices: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Compute MACD (Moving Average Convergence Divergence)."""
    ema_fast = prices.ewm(span=fast_period, adjust=False).mean()
    ema_slow = prices.ewm(span=slow_period, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


# Daily FRED series: series_id -> output column name (all US-only levels).
FRED_SERIES_IDS = [
    "FEDFUNDS",   # Effective federal funds rate
    "DGS2",       # 2y Treasury
    "DGS10",      # 10y Treasury
    "DGS30",      # 30y Treasury
    "T10Y2Y",     # 10y-2y spread
    "T10Y3M",     # 10y-3m spread
    "T10YIE",     # 10y breakeven inflation
    "SP500",      # S&P 500
    "VIXCLS",     # VIX
    "DTWEXBGS",   # Broad USD index
    "USEPUINDXD", # Economic Policy Uncertainty index
    "USRECD",     # Daily recession indicator
]

# Column names use _us suffix to reflect US-only source data (no differential logic).
_FRED_SERIES_TO_COLUMN = {
    "FEDFUNDS": "policy_rate_us",
    "DGS2": "interest_rate_2y_us",
    "DGS10": "interest_rate_10y_us",
    "DGS30": "dgs30_us",
    "T10Y2Y": "t10y2y_us",
    "T10Y3M": "t10y3m_us",
    "T10YIE": "t10yie_us",
    "SP500": "sp500_us",
    "VIXCLS": "vixcls_us",
    "DTWEXBGS": "dtwexbgs_us",
    "USEPUINDXD": "usepuindxd_us",
    "USRECD": "usrecd_us",
}

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _retry(func, max_attempts: int = 3, backoff: float = 2.0):
    """Call func with exponential backoff. Raises on final failure."""
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            wait = backoff ** attempt
            logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {wait:.1f}s")
            import time
            time.sleep(wait)


def _fetch_fred_series(
    series_id: str,
    api_key: str,
    observation_start: str,
    observation_end: str,
) -> pd.Series:
    """Fetch one FRED series and return a Series with date index and float values."""
    import requests

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "observation_end": observation_end,
    }

    def _do_request():
        r = requests.get(FRED_OBS_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    data = _retry(_do_request)
    obs = data.get("observations", [])
    rows = []
    for o in obs:
        date_str = o.get("date")
        val = o.get("value", ".")
        if date_str and val != ".":
            try:
                rows.append({"date": pd.to_datetime(date_str).date(), "value": float(val)})
            except (ValueError, TypeError):
                pass
    if not rows:
        return pd.Series(dtype=float)
    s = pd.DataFrame(rows).set_index("date")["value"]
    return s.sort_index()


def add_macro_features(
    df: pd.DataFrame,
    pair: str,
    config: Dict
) -> pd.DataFrame:
    """
    Add macroeconomic features from FRED (daily US series).
    Requires FRED_API_KEY in environment when macro is enabled; otherwise skips macro columns.
    Series list from config macro_indicators.fred_series, or default FRED_SERIES_IDS.
    """
    df = df.copy()
    macro_config = config.get("macro_indicators", {})

    if not macro_config.get("enabled", False):
        logger.info("Macro indicators disabled")
        return df

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logger.warning("FRED_API_KEY not set; skipping macro features")
        return df

    series_ids = macro_config.get("fred_series", FRED_SERIES_IDS)
    if not series_ids:
        return df

    logger.info(f"Adding macro features for {pair} (FRED daily, {len(series_ids)} series)")
    observation_start = pd.to_datetime(df["timestamp"]).min().strftime("%Y-%m-%d")
    observation_end = pd.to_datetime(df["timestamp"]).max().strftime("%Y-%m-%d")

    macro_series = {}
    for fred_id in series_ids:
        col_name = _FRED_SERIES_TO_COLUMN.get(fred_id, fred_id.lower() + "_diff")
        try:
            s = _fetch_fred_series(api_key=api_key, series_id=fred_id,
                                  observation_start=observation_start,
                                  observation_end=observation_end)
            if s.empty:
                logger.warning(f"FRED series {fred_id} returned no data")
                continue
            macro_series[col_name] = s
        except Exception as e:
            logger.warning(f"FRED fetch failed for {fred_id}: {e}")
            continue

    if not macro_series:
        return df

    # Build DataFrame with date index; reindex to all dates in df and forward-fill
    macro_df = pd.DataFrame(macro_series)
    df_dates = pd.to_datetime(df["timestamp"]).dt.normalize().dt.date
    unique_dates = sorted(df_dates.unique())
    aligned = macro_df.reindex(unique_dates).sort_index().ffill()
    df["_macro_date"] = df_dates
    for col in aligned.columns:
        df[col] = df["_macro_date"].map(aligned[col].to_dict())
    df.drop(columns=["_macro_date"], inplace=True)
    if macro_config.get("forward_fill", True):
        df[list(aligned.columns)] = df[list(aligned.columns)].ffill()
    return df


def process_data(pair: str, timeframe: str, output_path: Optional[str] = None) -> pd.DataFrame:
    """
    Main data processing pipeline.
    
    Args:
        pair: Currency pair (e.g., "USD_JPY")
        timeframe: Timeframe (e.g., "H1")
        output_path: Optional path to save processed data
    
    Returns:
        Processed DataFrame
    """
    logger.info(f"Processing data for {pair} {timeframe}")
    
    # Load configuration
    config = load_config()
    
    # Fetch data: DAYS_LOOK_BACK env (from secrets) overrides config
    lookback_days = config.get("data_sources", {}).get("forex", {}).get("lookback_days", 365)
    if os.environ.get("DAYS_LOOK_BACK"):
        try:
            lookback_days = int(os.environ["DAYS_LOOK_BACK"])
        except ValueError:
            logger.warning(f"Invalid DAYS_LOOK_BACK '{os.environ.get('DAYS_LOOK_BACK')}', using config: {lookback_days}")
    df = fetch_oanda_data(pair, timeframe, lookback_days)
    
    # Compute features
    df = compute_features(df, config)
    
    # Add macro features
    df = add_macro_features(df, pair, config)
    
    # Add metadata columns
    df["pair"] = pair
    df["timeframe"] = timeframe
    
    # Save if output path provided
    if output_path:
        df.to_csv(output_path, index=False)
        logger.info(f"Saved processed data to {output_path}")
    
    logger.info(f"Processing complete, final shape: {df.shape}")
    return df


def main():
    """Main entry point for data processing."""
    # Get parameters from environment or command line
    pair = os.environ.get("PAIR", "USD_JPY")
    timeframe = os.environ.get("TIMEFRAME", "H1")
    output_path = os.environ.get("OUTPUT_PATH", "/workspace/processed_data.csv")
    
    logger.info(f"Starting data processing: {pair} {timeframe}")
    
    try:
        df = process_data(pair, timeframe, output_path)
        logger.info(f"Successfully processed {len(df)} data points")
        return 0
    except Exception as e:
        logger.error(f"Data processing failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
