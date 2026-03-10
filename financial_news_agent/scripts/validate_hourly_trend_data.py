#!/usr/bin/env python3
"""
Validate data returned by the same ClickHouse query the API uses for hourly-trends.
Checks for NaN/Inf (and other non-JSON-serializable values) and attempts JSON encode
to confirm root cause of 500s before applying fixes.

Usage (from financial_news_scoring_api dir, same env as API):
  doppler run -- python scripts/validate_hourly_trend_data.py
  doppler run -- python scripts/validate_hourly_trend_data.py --symbol CAD --hours 48
  doppler run -- python scripts/validate_hourly_trend_data.py --symbol CAD --hours 48 72
"""

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect
import yaml

CONFIG_YAML_ENV = "CONFIG_YAML"
CONFIG_FILE = "config.yaml"


def load_config() -> dict:
    env_yaml = os.environ.get(CONFIG_YAML_ENV, "").strip()
    if env_yaml:
        return yaml.safe_load(env_yaml) or {}
    config_path = Path(__file__).resolve().parent.parent / CONFIG_FILE
    if config_path.is_file():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def get_ch_secrets() -> dict:
    required = {
        "CLICKHOUSE_HOST": os.environ.get("CLICKHOUSE_HOST"),
        "CLICKHOUSE_PORT": os.environ.get("CLICKHOUSE_PORT"),
        "CLICKHOUSE_USERNAME": os.environ.get("CLICKHOUSE_USERNAME"),
        "CLICKHOUSE_PASSWORD": os.environ.get("CLICKHOUSE_PASSWORD"),
    }
    missing = [k for k, v in required.items() if not (v and str(v).strip())]
    if missing:
        print(f"Missing env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return {k: (v.strip() if v else "") for k, v in required.items()}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate hourly_currency_scores data for NaN/Inf and JSON serialization."
    )
    parser.add_argument("--symbol", default="CAD", help="Symbol to query (default: CAD)")
    parser.add_argument(
        "--hours",
        type=int,
        nargs="+",
        default=[48, 72],
        help="Hour windows to query (default: 48 72)",
    )
    args = parser.parse_args()

    config = load_config()
    secrets = get_ch_secrets()
    ch_db = config.get("clickhouse", {})
    db = ch_db.get("database") or os.environ.get("CLICKHOUSE_DATABASE", "financial_news_scoring")
    view_scores = "hourly_currency_scores"
    secure = os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes")

    client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db,
        secure=secure,
    )

    for hours in args.hours:
        print(f"\n--- symbol={args.symbol} hours={hours} ---")
        q = f"""
        SELECT *
        FROM {db}.{view_scores}
        WHERE symbol = {{sym:String}} AND hour_bucket >= now() - INTERVAL {{hrs:UInt32}} HOUR
        ORDER BY hour_bucket DESC
        """
        try:
            r = client.query(q, parameters={"sym": args.symbol, "hrs": hours})
        except Exception as e:
            print(f"Query error: {e}")
            continue
        columns = r.column_names or []
        rows = [dict(zip(columns, row)) for row in (r.result_rows or [])]
        print(f"Row count: {len(rows)}")

        # 1) Scan for NaN/Inf and other non-JSON-serializable values
        bad = []
        for i, row in enumerate(rows):
            for col, v in row.items():
                if isinstance(v, float):
                    if math.isnan(v):
                        bad.append((i, col, "NaN"))
                    elif math.isinf(v):
                        bad.append((i, col, "Inf" if v > 0 else "-Inf"))
                elif hasattr(v, "isoformat"):
                    pass  # datetime is JSON-serializable when converted
                elif v is None or isinstance(v, (bool, int, str)):
                    pass
                else:
                    bad.append((i, col, repr(type(v).__name__)))

        if bad:
            print("Non-JSON-serializable or special float values:")
            for i, col, kind in bad:
                print(f"  row={i} col={col} -> {kind}")
        else:
            print("No NaN/Inf or other flagged values in raw row cells.")

        # 2) Build response body like the API (datetimes to isoformat, no NaN sanitization)
        for row in rows:
            for k, v in list(row.items()):
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        body = {"symbol": args.symbol, "hours": hours, "rows": rows}

        # 3) Attempt JSON encode like FastAPI
        try:
            json.dumps(body, default=str)
            print("JSON encode: OK")
        except Exception as e:
            print(f"JSON encode error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
