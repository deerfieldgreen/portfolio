#!/usr/bin/env python3
"""
Query currency scores from the news_agent ClickHouse tables.

Two sources:
  snapshots   – pre-aggregated decayed scores (run at end of each pipeline cycle).
                Best for "current" score: -1.0 (bearish) to +1.0 (bullish).
  news_items  – raw article scores. Use for history or custom aggregation.

Usage:
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_currency_score.py
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_currency_score.py --currency USD
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_currency_score.py --source news_items --hours 24
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent so we can import scoring_pipeline's load_config and get_secrets_from_env
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect


def _get_client():
    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
    table_snapshots = ch_db.get("table_snapshots", "snapshots")
    table_news = ch_db.get("table_news_items", "news_items")
    secure = os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes")

    client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db_name,
        secure=secure,
    )
    return client, db_name, table_snapshots, table_news


def query_snapshots(client, db_name: str, table_snapshots: str, currency: str | None) -> None:
    """Latest decayed score from snapshots (per-currency)."""
    if currency:
        q = f"SELECT symbol, decayed_score, article_count, timestamp FROM {table_snapshots} WHERE symbol = {{sym:String}} ORDER BY timestamp DESC LIMIT 1"
        result = client.query(q, parameters={"sym": currency})
    else:
        q = f"""
        SELECT symbol, argMax(decayed_score, timestamp) AS decayed_score, argMax(article_count, timestamp) AS article_count, max(timestamp) AS timestamp
        FROM {table_snapshots}
        GROUP BY symbol
        ORDER BY symbol
        """
        result = client.query(q)

    rows = result.result_rows
    if not rows:
        print("No snapshot data. Run the pipeline at least once to populate snapshots.")
        return

    print("Snapshot (decayed) scores – latest per currency:")
    print("-" * 60)
    for r in rows:
        sym, score, count, ts = r
        bar = "█" * int((score + 1) * 10) + "░" * (20 - int((score + 1) * 10))
        print(f"  {sym}: {score:+.2f}  {bar}  ({count} articles, {ts})")


def query_news_items(
    client, db_name: str, table_news: str, currency: str | None, hours: int
) -> None:
    """Raw scores from news_items, optionally aggregated."""
    bias_field = f"{currency.lower()}_bias" if currency else None
    if currency and currency.upper() in ("USD", "EUR", "JPY", "GBP"):
        bias_field = f"{currency.lower()}_bias"
    elif currency:
        print(f"Unknown currency {currency}. Use USD, EUR, JPY, or GBP for news_items bias.")
        return

    window = f"timestamp >= now() - INTERVAL {hours} HOUR"

    if bias_field:
        q = f"""
        SELECT
          round(avg(JSONExtractFloat(scores, '{bias_field}')), 4) AS avg_bias,
          count() AS article_count
        FROM {table_news}
        WHERE {window}
        """
        result = client.query(q)
        rows = result.result_rows
        if rows:
            avg_bias, count = rows[0]
            print(f"News items (last {hours}h) – {currency} bias:")
            print("-" * 60)
            print(f"  avg {currency}_bias: {avg_bias:+.2f}  ({count} articles)")
        else:
            print(f"No articles in last {hours} hours.")
    else:
        q = f"""
        SELECT
          round(avg(JSONExtractFloat(scores, 'usd_bias')), 4) AS usd,
          round(avg(JSONExtractFloat(scores, 'eur_bias')), 4) AS eur,
          round(avg(JSONExtractFloat(scores, 'jpy_bias')), 4) AS jpy,
          round(avg(JSONExtractFloat(scores, 'gbp_bias')), 4) AS gbp,
          count() AS cnt
        FROM {table_news}
        WHERE {window}
        """
        result = client.query(q)
        rows = result.result_rows
        if rows:
            usd, eur, jpy, gbp, cnt = rows[0]
            print(f"News items (last {hours}h) – average bias per currency:")
            print("-" * 60)
            print(f"  USD: {usd:+.2f}  EUR: {eur:+.2f}  JPY: {jpy:+.2f}  GBP: {gbp:+.2f}  ({cnt} articles)")
        else:
            print(f"No articles in last {hours} hours.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query currency scores from news_agent")
    parser.add_argument("--currency", "-c", help="Currency: USD, EUR, JPY, GBP")
    parser.add_argument("--source", choices=["snapshots", "news_items"], default="snapshots")
    parser.add_argument("--hours", type=int, default=24, help="Window for news_items (default 24)")
    args = parser.parse_args()

    client, db_name, table_snapshots, table_news = _get_client()

    if args.source == "snapshots":
        query_snapshots(client, db_name, table_snapshots, args.currency)
    else:
        query_news_items(client, db_name, table_news, args.currency, args.hours)


if __name__ == "__main__":
    main()
