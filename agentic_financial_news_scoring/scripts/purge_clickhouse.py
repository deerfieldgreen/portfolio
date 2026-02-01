#!/usr/bin/env python3
"""
Purge news_agent ClickHouse tables for testing. Clears news_items and hourly_currency_scores
so the pipeline can re-ingest articles without duplicate skips.

Usage:
  doppler run --project tavily_news_agent --config dev -- python3 scripts/purge_clickhouse.py --yes
  doppler run --project tavily_news_agent --config dev -- python3 scripts/purge_clickhouse.py -y
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge news_agent ClickHouse tables (news_items, hourly_currency_scores) for testing."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Confirm purge; without this, script exits without changing anything",
    )
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to purge without --yes / -y. Run: python3 scripts/purge_clickhouse.py --yes")
        sys.exit(1)

    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
    table_news = ch_db.get("table_news_items", "news_items")
    table_hourly = ch_db.get("table_hourly_scores", "hourly_currency_scores")
    secure = os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes")

    client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db_name,
        secure=secure,
    )

    # Truncate both tables; order does not matter
    client.command(f"TRUNCATE TABLE {db_name}.{table_hourly}")
    print(f"Truncated {db_name}.{table_hourly}")

    client.command(f"TRUNCATE TABLE {db_name}.{table_news}")
    print(f"Truncated {db_name}.{table_news}")

    print("Purge complete. You can now run the pipeline to re-ingest articles.")


if __name__ == "__main__":
    main()
