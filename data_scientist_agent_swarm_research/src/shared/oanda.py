"""OANDA candle fetch via oanda-caching-api with retry."""
import os
from typing import List, Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(int(os.environ.get("OANDA_FETCH_RETRIES", "3"))),
    wait=wait_exponential(
        multiplier=float(os.environ.get("OANDA_FETCH_BACKOFF_BASE", "2.0")),
        min=1,
        max=30,
    ),
)
def fetch_candles(
    instrument: str,
    granularity: str,
    count: int = 500,
    proxy_url: str = None,
) -> List[Dict]:
    """
    Fetch candles from oanda-caching-api.
    Returns list of dicts with keys: time, open, high, low, close, volume.
    """
    base_url = proxy_url or os.environ.get("OANDA_PROXY_URL", "http://oanda-cache:8080")
    url = f"{base_url}/v3/instruments/{instrument}/candles"

    with httpx.Client(timeout=30) as client:
        resp = client.get(url, params={
            "granularity": granularity,
            "count": count,
            "price": "M",
        })
        resp.raise_for_status()
        data = resp.json()

    candles = []
    for c in data.get("candles", []):
        mid = c.get("mid", {})
        candles.append({
            "time": c["time"],
            "open": float(mid.get("o", 0)),
            "high": float(mid.get("h", 0)),
            "low": float(mid.get("l", 0)),
            "close": float(mid.get("c", 0)),
            "volume": float(c.get("volume", 0)),
        })

    return candles
