#!/usr/bin/env python3
"""
fetch_data.py: Fetch OHLCV data from Oanda API using oandapyV20 (v20 API).
Supports USD_JPY and EUR_USD with M30, H1, H4 timeframes.
Uses practice account by default; only OANDA_API_KEY required (no account ID).
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from oandapyV20 import API
from oandapyV20.contrib.factories import InstrumentsCandlesFactory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Oanda practice server (no account ID needed for candles)
OANDA_PRACTICE_ENVIRONMENT = "practice"


def convert_symbol_format(symbol: str) -> str:
    """Convert symbol format: USDJPY -> USD_JPY (Oanda format)."""
    if "_" in symbol:
        return symbol
    if len(symbol) == 6:
        return f"{symbol[:3]}_{symbol[3:]}"
    return symbol


def _date_to_rfc3339(date_str: str, end_of_day: bool = False) -> str:
    """Convert YYYY-MM-DD to Oanda RFC3339 (UTC), no fractional seconds."""
    if end_of_day:
        return f"{date_str}T23:59:59Z"
    return f"{date_str}T00:00:00Z"


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str = None,
    access_token: str = None,
    environment: str = OANDA_PRACTICE_ENVIRONMENT,
) -> pd.DataFrame:
    """
    Fetch OHLCV data from Oanda v20 API (instruments/candles).

    Args:
        symbol: Trading pair (e.g., 'USD_JPY', 'EUR_USD')
        timeframe: Granularity ('M30', 'H1', 'H4')
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD' (defaults to today)
        access_token: Oanda API key (defaults to OANDA_API_KEY env)
        environment: 'practice' or 'live'

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    token = access_token or os.environ.get("OANDA_API_KEY")
    if not token:
        raise ValueError(
            "OANDA_API_KEY not set. Set the environment variable or pass access_token."
        )

    if end_date is None:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    oanda_symbol = convert_symbol_format(symbol)
    from_param = _date_to_rfc3339(start_date)
    to_param = _date_to_rfc3339(end_date, end_of_day=True)

    client = API(access_token=token, environment=environment)
    logger.info(f"Fetching {oanda_symbol} {timeframe} from {start_date} to {end_date} ({environment})")

    params = {
        "from": from_param,
        "to": to_param,
        "granularity": timeframe,
    }

    rows = []
    for request in InstrumentsCandlesFactory(instrument=oanda_symbol, params=params):
        try:
            client.request(request)
        except Exception as e:
            logger.error(f"Oanda request failed: {e}")
            raise
        data = request.response.get("candles", [])
        for c in data:
            if not c.get("complete", True):
                continue
            mid = c.get("mid") or {}
            rows.append({
                "timestamp": c.get("time", "")[:19].replace("T", " ").replace("Z", ""),
                "open": float(mid.get("o", 0)),
                "high": float(mid.get("h", 0)),
                "low": float(mid.get("l", 0)),
                "close": float(mid.get("c", 0)),
                "volume": int(c.get("volume", 0)),
            })

    if not rows:
        logger.warning(f"No candles returned for {oanda_symbol} {timeframe}")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    data = pd.DataFrame(rows)
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    logger.info(f"Fetched {len(data)} bars for {symbol}")
    return data


def save_to_csv(data: pd.DataFrame, symbol: str, timeframe: str, output_dir: str = "/app/data") -> str:
    """Save data to CSV file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_{timeframe}.csv"
    filepath = Path(output_dir) / filename
    data.to_csv(filepath, index=False)
    logger.info(f"Saved data to {filepath}")
    return str(filepath)


def main():
    parser = argparse.ArgumentParser(description="Fetch OHLCV data from Oanda v20 API")
    parser.add_argument("--symbol", required=True, help="Trading pair (e.g., USD_JPY, EUR_USD)")
    parser.add_argument("--timeframe", required=True, help="Timeframe (M30, H1, H4)")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--environment", default=OANDA_PRACTICE_ENVIRONMENT, choices=["practice", "live"],
                        help="Oanda environment (default: practice)")
    parser.add_argument("--output-dir", default="/app/data", help="Output directory for CSV files")
    args = parser.parse_args()

    try:
        data = fetch_ohlcv(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date,
            environment=args.environment,
        )
        filepath = save_to_csv(data, args.symbol, args.timeframe, args.output_dir)
        print(f"SUCCESS: {filepath}")
        return 0
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
