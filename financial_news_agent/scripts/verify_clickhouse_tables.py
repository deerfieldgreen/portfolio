#!/usr/bin/env python3
"""
Verify data in financial_news_scoring ClickHouse tables: news_items, hourly/minute currency score tables and VIEWs.
Queries ClickHouse directly. Use after init or after running the pipeline / create_mv_hourly_scores / create_mv_minute_scores.

Usage:
  doppler run -- python3 scripts/verify_clickhouse_tables.py
  doppler run -- python3 scripts/verify_clickhouse_tables.py --hours 168
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify data in financial_news_scoring ClickHouse tables (news_items, hourly_currency_scores)."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Lookback hours for sample queries (default 24)",
    )
    args = parser.parse_args()

    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db = ch_db.get("database", "financial_news_scoring")
    table_news = ch_db.get("table_news_items", "fn_news_items")
    table_states = ch_db.get("table_hourly_score_states", "hourly_currency_score_states")
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

    def run(q: str, title: str) -> list:
        print(f"\n--- {title} ---")
        try:
            r = client.query(q)
            rows = r.result_rows
            if r.column_names:
                print("Columns:", r.column_names)
            for row in rows:
                print(row)
            return rows
        except Exception as e:
            print(f"Error: {e}")
            return []

    # 1) news_items
    run(
        f"""
        SELECT
            count() AS total_rows,
            min(timestamp) AS min_ts,
            max(timestamp) AS max_ts,
            countIf(primary_ccy != '') AS with_primary_ccy
        FROM {db}.{table_news}
        """,
        f"1. {table_news} (counts)",
    )
    run(
        f"""
        SELECT primary_ccy, count() AS cnt
        FROM {db}.{table_news}
        WHERE primary_ccy != ''
        GROUP BY primary_ccy
        ORDER BY cnt DESC
        """,
        f"2. {table_news} (rows per primary_ccy)",
    )
    run(
        f"""
        SELECT id, timestamp, primary_ccy, volatility_impact, timeliness, bearish_prob, bullish_prob, neutral_prob
        FROM {db}.{table_news}
        WHERE primary_ccy != ''
        ORDER BY timestamp DESC
        LIMIT 3
        """,
        f"3. {table_news} (latest 3 rows, score columns)",
    )

    # 4) hourly_currency_score_states (raw row count; states are binary)
    run(
        f"""
        SELECT count() AS state_rows
        FROM {db}.{table_states}
        """,
        f"4. {table_states} (row count)",
    )

    # 5) hourly_currency_scores VIEW (merged stats)
    run(
        f"""
        SELECT
            count() AS total_rows,
            min(hour_bucket) AS min_hour,
            max(hour_bucket) AS max_hour
        FROM {db}.{view_scores}
        """,
        f"5. {view_scores} (counts)",
    )
    run(
        f"""
        SELECT hour_bucket, symbol, article_count,
               volatility_impact_mean, volatility_impact_stddev, volatility_impact_p50,
               timeliness_mean, bearish_prob_mean, bullish_prob_mean, neutral_prob_mean
        FROM {db}.{view_scores}
        WHERE hour_bucket >= now() - INTERVAL {args.hours} HOUR
        ORDER BY hour_bucket DESC, symbol
        LIMIT 15
        """,
        f"6. {view_scores} (sample last {args.hours}h)",
    )

    # 7) Minute-level (if created via create_mv_minute_scores.py)
    run(
        f"""
        SELECT count() AS rows_in_view
        FROM {db}.minute_currency_scores_last_100
        """,
        "7. minute_currency_scores_last_100 (row count)",
    )
    run(
        f"""
        SELECT minute_bucket, symbol, article_count, volatility_impact_mean, volatility_impact_p50
        FROM {db}.minute_currency_scores_last_100
        ORDER BY minute_bucket DESC, symbol
        LIMIT 10
        """,
        "8. minute_currency_scores_last_100 (sample)",
    )

    print("\n--- Done ---\n")


if __name__ == "__main__":
    main()
