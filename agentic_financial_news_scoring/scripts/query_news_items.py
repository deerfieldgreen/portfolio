#!/usr/bin/env python3
"""
Query news_items table for analysis. Displays articles with scores, summary, and optional raw content.

Supports both NEWS_SCORE_V1.1 schema (primary_currency, bearish, bullish, neutral, etc.)
and legacy schema (usd_bias, eur_bias, etc.).

Usage:
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_news_items.py
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_news_items.py --hours 168 --limit 20
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_news_items.py --currency USD --csv
  doppler run --project tavily_news_agent --config dev -- python3 scripts/query_news_items.py --verbose
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clickhouse_connect


def _get_client():
    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
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
    return client, db_name, table_news


def _safe_float(obj: dict, key: str) -> float | None:
    v = obj.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _format_scores(scores: dict) -> str:
    """Compact one-line representation of scores."""
    parts = []
    if scores.get("primary_currency"):
        parts.append(f"ccy={scores['primary_currency']}")
    for k in ("bearish", "bullish", "neutral"):
        v = _safe_float(scores, k)
        if v is not None:
            parts.append(f"{k}={v:.2f}")
    for k in ("timeliness_score", "volatility_impact", "confidence"):
        v = _safe_float(scores, k)
        if v is not None:
            short = "timeliness" if k == "timeliness_score" else k
            parts.append(f"{short}={v:.2f}")
    # Legacy bias fields
    for k in ("usd_bias", "eur_bias", "gbp_bias", "jpy_bias"):
        v = _safe_float(scores, k)
        if v is not None:
            parts.append(f"{k}={v:.2f}")
    return " | ".join(parts) if parts else "(no scores)"


def run_query(
    client,
    table_news: str,
    hours: int,
    limit: int,
    currency: str | None,
) -> list[tuple]:
    where_parts = [f"timestamp >= now() - INTERVAL {hours} HOUR"]
    params: dict = {}
    if currency:
        where_parts.append("JSONExtractString(scores, 'primary_currency') = {ccy:String}")
        params["ccy"] = currency.upper()
    where = " AND ".join(where_parts)

    q = f"""
    SELECT id, timestamp, url, symbols, summary, scores, raw_text
    FROM {table_news}
    WHERE {where}
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    result = client.query(q, parameters=params) if params else client.query(q)
    return result.result_rows


def print_table(rows: list[tuple], verbose: bool, raw_preview_len: int = 400) -> None:
    for i, r in enumerate(rows, 1):
        id_, ts, url, symbols, summary, scores_str, raw_text = r
        scores = json.loads(scores_str) if scores_str else {}
        summary = (summary or "").strip() or "(no summary)"
        url_short = (url or "")[:80] + ("..." if len(url or "") > 80 else "")

        print(f"\n{'='*80}")
        print(f"[{i}] {id_}")
        print(f"    timestamp: {ts}  |  symbols: {symbols}")
        print(f"    url: {url_short}")
        print(f"    summary: {summary}")
        print(f"    scores: {_format_scores(scores)}")
        if verbose and raw_text:
            preview = (raw_text[:raw_preview_len] + "...") if len(raw_text) > raw_preview_len else raw_text
            print(f"    raw_text: {preview}")


def print_csv(rows: list[tuple]) -> None:
    if not rows:
        return
    fieldnames = [
        "id", "timestamp", "url", "symbols", "summary",
        "primary_currency", "bearish", "bullish", "neutral",
        "timeliness_score", "volatility_impact", "confidence",
        "affected_pairs", "usd_bias", "eur_bias", "gbp_bias", "jpy_bias",
    ]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        id_, ts, url, symbols, summary, scores_str, raw_text = r
        scores = json.loads(scores_str) if scores_str else {}
        row = {
            "id": id_,
            "timestamp": str(ts),
            "url": url or "",
            "symbols": ",".join(symbols) if symbols else "",
            "summary": (summary or "").strip(),
        }
        for k in ("primary_currency", "bearish", "bullish", "neutral", "timeliness_score", "volatility_impact", "confidence"):
            v = scores.get(k)
            row[k] = v if v is not None else ""
        row["affected_pairs"] = ",".join(scores.get("affected_pairs", [])) if scores.get("affected_pairs") else ""
        for k in ("usd_bias", "eur_bias", "gbp_bias", "jpy_bias"):
            row[k] = scores.get(k) if scores.get(k) is not None else ""
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query news_items table for analysis of scored articles."
    )
    parser.add_argument("--hours", "-H", type=int, default=168, help="Time window in hours (default 168 = 1 week)")
    parser.add_argument("--limit", "-n", type=int, default=50, help="Max articles to return (default 50)")
    parser.add_argument("--currency", "-c", help="Filter by primary_currency (USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Include raw_text preview per article")
    parser.add_argument("--csv", action="store_true", help="Output as CSV for spreadsheet analysis")
    args = parser.parse_args()

    client, db_name, table_news = _get_client()
    rows = run_query(client, table_news, args.hours, args.limit, args.currency)

    if not rows:
        print(f"No articles in last {args.hours}h" + (f" for {args.currency}" if args.currency else "") + ".")
        sys.exit(0)

    print(f"Found {len(rows)} articles (last {args.hours}h" + (f", primary_currency={args.currency}" if args.currency else "") + ")")
    if args.csv:
        print_csv(rows)
    else:
        print_table(rows, args.verbose)


if __name__ == "__main__":
    main()
