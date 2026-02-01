#!/usr/bin/env python3
"""
Create materialized view from news_items: group by symbol and each hour;
for each score (bearish, bullish, neutral, timeliness, volatility_impact, confidence)
compute min, max, avg, stddev, skew, kurtosis. Target table uses AggregatingMergeTree.
Query final stats via VIEW hourly_currency_score_stats.

Usage:
  doppler run --project tavily_news_agent --config dev -- python3 scripts/create_mv_hourly_scores.py
  doppler run --project tavily_news_agent --config dev -- python3 scripts/create_mv_hourly_scores.py --no-backfill
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create MV from news_items: hourly by symbol with min/max/avg/stddev/skew/kurtosis per score."
    )
    parser.add_argument(
        "--no-backfill",
        action="store_true",
        help="Skip backfilling from existing news_items",
    )
    args = parser.parse_args()

    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
    table_news = ch_db.get("table_news_items", "news_items")
    table_states = "hourly_currency_score_states"
    mv_name = "mv_hourly_currency_score_states"
    view_name = "hourly_currency_score_stats"
    secure = os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes")

    client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db_name,
        secure=secure,
    )

    # 1) Drop MV and VIEW first (VIEW depends on table), then drop table, recreate table
    client.command(f"DROP MATERIALIZED VIEW IF EXISTS {db_name}.{mv_name}")
    client.command(f"DROP VIEW IF EXISTS {db_name}.{view_name}")
    client.command(f"DROP TABLE IF EXISTS {db_name}.{table_states}")

    # 2) Create target table (AggregatingMergeTree, one row per (hour_bucket, symbol) with states)
    client.command(f"""
    CREATE TABLE {db_name}.{table_states}
    (
        hour_bucket   DateTime,
        symbol         String,
        article_count  AggregateFunction(count, UInt64),
        bearish_min    AggregateFunction(min, Float32),
        bearish_max    AggregateFunction(max, Float32),
        bearish_avg    AggregateFunction(avg, Float32),
        bearish_stddev AggregateFunction(stddevPop, Float32),
        bearish_skew   AggregateFunction(skewPop, Float32),
        bearish_kurt   AggregateFunction(kurtPop, Float32),
        bullish_min    AggregateFunction(min, Float32),
        bullish_max    AggregateFunction(max, Float32),
        bullish_avg    AggregateFunction(avg, Float32),
        bullish_stddev AggregateFunction(stddevPop, Float32),
        bullish_skew   AggregateFunction(skewPop, Float32),
        bullish_kurt   AggregateFunction(kurtPop, Float32),
        neutral_min    AggregateFunction(min, Float32),
        neutral_max    AggregateFunction(max, Float32),
        neutral_avg    AggregateFunction(avg, Float32),
        neutral_stddev AggregateFunction(stddevPop, Float32),
        neutral_skew   AggregateFunction(skewPop, Float32),
        neutral_kurt   AggregateFunction(kurtPop, Float32),
        timeliness_min    AggregateFunction(min, Float32),
        timeliness_max    AggregateFunction(max, Float32),
        timeliness_avg    AggregateFunction(avg, Float32),
        timeliness_stddev AggregateFunction(stddevPop, Float32),
        timeliness_skew   AggregateFunction(skewPop, Float32),
        timeliness_kurt   AggregateFunction(kurtPop, Float32),
        volatility_impact_min    AggregateFunction(min, Float32),
        volatility_impact_max    AggregateFunction(max, Float32),
        volatility_impact_avg    AggregateFunction(avg, Float32),
        volatility_impact_stddev AggregateFunction(stddevPop, Float32),
        volatility_impact_skew   AggregateFunction(skewPop, Float32),
        volatility_impact_kurt   AggregateFunction(kurtPop, Float32),
        confidence_min    AggregateFunction(min, Float32),
        confidence_max    AggregateFunction(max, Float32),
        confidence_avg    AggregateFunction(avg, Float32),
        confidence_stddev AggregateFunction(stddevPop, Float32),
        confidence_skew   AggregateFunction(skewPop, Float32),
        confidence_kurt   AggregateFunction(kurtPop, Float32)
    )
    ENGINE = AggregatingMergeTree()
    ORDER BY (hour_bucket, symbol)
    """)
    print(f"Created {db_name}.{table_states}.")

    # 3) Create MV
    client.command(f"""
    CREATE MATERIALIZED VIEW {db_name}.{mv_name}
    TO {db_name}.{table_states}
    AS
    SELECT
        toStartOfHour(timestamp) AS hour_bucket,
        primary_ccy AS symbol,
        countState() AS article_count,
        minState(bearish_prob) AS bearish_min,
        maxState(bearish_prob) AS bearish_max,
        avgState(bearish_prob) AS bearish_avg,
        stddevPopState(bearish_prob) AS bearish_stddev,
        skewPopState(bearish_prob) AS bearish_skew,
        kurtPopState(bearish_prob) AS bearish_kurt,
        minState(bullish_prob) AS bullish_min,
        maxState(bullish_prob) AS bullish_max,
        avgState(bullish_prob) AS bullish_avg,
        stddevPopState(bullish_prob) AS bullish_stddev,
        skewPopState(bullish_prob) AS bullish_skew,
        kurtPopState(bullish_prob) AS bullish_kurt,
        minState(neutral_prob) AS neutral_min,
        maxState(neutral_prob) AS neutral_max,
        avgState(neutral_prob) AS neutral_avg,
        stddevPopState(neutral_prob) AS neutral_stddev,
        skewPopState(neutral_prob) AS neutral_skew,
        kurtPopState(neutral_prob) AS neutral_kurt,
        minState(timeliness) AS timeliness_min,
        maxState(timeliness) AS timeliness_max,
        avgState(timeliness) AS timeliness_avg,
        stddevPopState(timeliness) AS timeliness_stddev,
        skewPopState(timeliness) AS timeliness_skew,
        kurtPopState(timeliness) AS timeliness_kurt,
        minState(volatility_impact) AS volatility_impact_min,
        maxState(volatility_impact) AS volatility_impact_max,
        avgState(volatility_impact) AS volatility_impact_avg,
        stddevPopState(volatility_impact) AS volatility_impact_stddev,
        skewPopState(volatility_impact) AS volatility_impact_skew,
        kurtPopState(volatility_impact) AS volatility_impact_kurt,
        minState(confidence) AS confidence_min,
        maxState(confidence) AS confidence_max,
        avgState(confidence) AS confidence_avg,
        stddevPopState(confidence) AS confidence_stddev,
        skewPopState(confidence) AS confidence_skew,
        kurtPopState(confidence) AS confidence_kurt
    FROM {db_name}.{table_news}
    WHERE primary_ccy != ''
    GROUP BY hour_bucket, symbol
    """)
    print(f"Created {db_name}.{mv_name} -> {db_name}.{table_states}.")

    # 4) Create VIEW for readable stats (finalize states with -Merge)
    client.command(f"""
    CREATE VIEW {db_name}.{view_name} AS
    SELECT
        hour_bucket,
        symbol,
        countMerge(article_count) AS article_count,
        minMerge(bearish_min) AS bearish_min,
        maxMerge(bearish_max) AS bearish_max,
        avgMerge(bearish_avg) AS bearish_avg,
        stddevPopMerge(bearish_stddev) AS bearish_stddev,
        skewPopMerge(bearish_skew) AS bearish_skew,
        kurtPopMerge(bearish_kurt) AS bearish_kurtosis,
        minMerge(bullish_min) AS bullish_min,
        maxMerge(bullish_max) AS bullish_max,
        avgMerge(bullish_avg) AS bullish_avg,
        stddevPopMerge(bullish_stddev) AS bullish_stddev,
        skewPopMerge(bullish_skew) AS bullish_skew,
        kurtPopMerge(bullish_kurt) AS bullish_kurtosis,
        minMerge(neutral_min) AS neutral_min,
        maxMerge(neutral_max) AS neutral_max,
        avgMerge(neutral_avg) AS neutral_avg,
        stddevPopMerge(neutral_stddev) AS neutral_stddev,
        skewPopMerge(neutral_skew) AS neutral_skew,
        kurtPopMerge(neutral_kurt) AS neutral_kurtosis,
        minMerge(timeliness_min) AS timeliness_min,
        maxMerge(timeliness_max) AS timeliness_max,
        avgMerge(timeliness_avg) AS timeliness_avg,
        stddevPopMerge(timeliness_stddev) AS timeliness_stddev,
        skewPopMerge(timeliness_skew) AS timeliness_skew,
        kurtPopMerge(timeliness_kurt) AS timeliness_kurtosis,
        minMerge(volatility_impact_min) AS volatility_impact_min,
        maxMerge(volatility_impact_max) AS volatility_impact_max,
        avgMerge(volatility_impact_avg) AS volatility_impact_avg,
        stddevPopMerge(volatility_impact_stddev) AS volatility_impact_stddev,
        skewPopMerge(volatility_impact_skew) AS volatility_impact_skew,
        kurtPopMerge(volatility_impact_kurt) AS volatility_impact_kurtosis,
        minMerge(confidence_min) AS confidence_min,
        maxMerge(confidence_max) AS confidence_max,
        avgMerge(confidence_avg) AS confidence_avg,
        stddevPopMerge(confidence_stddev) AS confidence_stddev,
        skewPopMerge(confidence_skew) AS confidence_skew,
        kurtPopMerge(confidence_kurt) AS confidence_kurtosis
    FROM {db_name}.{table_states}
    GROUP BY hour_bucket, symbol
    """)
    print(f"Created VIEW {db_name}.{view_name}.")

    # 5) Backfill
    if not args.no_backfill:
        client.command(f"""
        INSERT INTO {db_name}.{table_states}
        SELECT
            toStartOfHour(timestamp) AS hour_bucket,
            primary_ccy AS symbol,
            countState() AS article_count,
            minState(bearish_prob) AS bearish_min,
            maxState(bearish_prob) AS bearish_max,
            avgState(bearish_prob) AS bearish_avg,
            stddevPopState(bearish_prob) AS bearish_stddev,
            skewPopState(bearish_prob) AS bearish_skew,
            kurtPopState(bearish_prob) AS bearish_kurt,
            minState(bullish_prob) AS bullish_min,
            maxState(bullish_prob) AS bullish_max,
            avgState(bullish_prob) AS bullish_avg,
            stddevPopState(bullish_prob) AS bullish_stddev,
            skewPopState(bullish_prob) AS bullish_skew,
            kurtPopState(bullish_prob) AS bullish_kurt,
            minState(neutral_prob) AS neutral_min,
            maxState(neutral_prob) AS neutral_max,
            avgState(neutral_prob) AS neutral_avg,
            stddevPopState(neutral_prob) AS neutral_stddev,
            skewPopState(neutral_prob) AS neutral_skew,
            kurtPopState(neutral_prob) AS neutral_kurt,
            minState(timeliness) AS timeliness_min,
            maxState(timeliness) AS timeliness_max,
            avgState(timeliness) AS timeliness_avg,
            stddevPopState(timeliness) AS timeliness_stddev,
            skewPopState(timeliness) AS timeliness_skew,
            kurtPopState(timeliness) AS timeliness_kurt,
            minState(volatility_impact) AS volatility_impact_min,
            maxState(volatility_impact) AS volatility_impact_max,
            avgState(volatility_impact) AS volatility_impact_avg,
            stddevPopState(volatility_impact) AS volatility_impact_stddev,
            skewPopState(volatility_impact) AS volatility_impact_skew,
            kurtPopState(volatility_impact) AS volatility_impact_kurt,
            minState(confidence) AS confidence_min,
            maxState(confidence) AS confidence_max,
            avgState(confidence) AS confidence_avg,
            stddevPopState(confidence) AS confidence_stddev,
            skewPopState(confidence) AS confidence_skew,
            kurtPopState(confidence) AS confidence_kurt
        FROM {db_name}.{table_news}
        WHERE primary_ccy != ''
        GROUP BY hour_bucket, symbol
        """)
        print("Backfilled from existing news_items.")
    else:
        print("Skipped backfill (--no-backfill).")

    print("Done. Query stats with: SELECT * FROM " + f"{db_name}.{view_name}" + " [WHERE ...].")


if __name__ == "__main__":
    main()
