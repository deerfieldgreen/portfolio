"""
Extract training data from ClickHouse to parquet file.
Runs in fx-ops image. Output: /workspace/data.parquet
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import pandas as pd
from src.shared.ch_client import get_client
from src.shared.config import SharedConfig

cfg = SharedConfig()


def main():
    pair = os.environ["PAIR"]
    timeframe = os.environ["TIMEFRAME"]
    output_path = os.environ.get("OUTPUT_PATH", "/workspace/data.parquet")

    ch = get_client()

    # Fetch all features for this pair/TF
    result = ch.query(
        "SELECT timestamp, open, high, low, close, volume, features "
        "FROM fxs_instrument_features "
        "WHERE pair = %(pair)s AND timeframe = %(tf)s "
        "ORDER BY timestamp ASC",
        parameters={"pair": pair, "tf": timeframe},
    )

    if result.row_count == 0:
        print(f"No data found for {pair}/{timeframe}")
        return

    rows = result.named_results()
    records = []
    for row in rows:
        record = {
            "timestamp": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        # Flatten feature map
        for k, v in (row.get("features") or {}).items():
            record[k] = v
        records.append(record)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df.to_parquet(output_path)
    print(f"Extracted {len(df)} rows to {output_path}")


if __name__ == "__main__":
    main()
