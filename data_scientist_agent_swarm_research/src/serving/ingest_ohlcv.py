"""Fetch OHLCV candles from oanda-caching-api."""
from typing import List, Dict
from src.shared.oanda import fetch_candles


def ingest(instrument: str, granularity: str, count: int = 500) -> List[Dict]:
    """
    Fetch candles. Returns list of dicts with keys:
    time, open, high, low, close, volume
    """
    return fetch_candles(
        instrument=instrument,
        granularity=granularity,
        count=count,
    )
