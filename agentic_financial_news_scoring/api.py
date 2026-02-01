#!/usr/bin/env python3
"""
FastAPI reporting API for news_agent scores and articles.

Topic 1 (hourly scores by currency): materialized view hourly_currency_scores in ClickHouse.
Topic 2 (hourly decay): applied in code in GET /scores and GET /scores/{currency}.

Run: doppler run --project tavily_news_agent --config dev -- uvicorn api:app --host 0.0.0.0 --port 8000
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(
    title="news_agent API",
    description="Currency scores and news articles from the scoring pipeline.",
)


def _get_client():
    from scoring_pipeline import get_secrets_from_env, load_config

    config = load_config()
    secrets = get_secrets_from_env()
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
    secure = os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes")

    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db_name,
        secure=secure,
    )
    table_hourly_scores = ch_db.get("table_hourly_scores", "hourly_currency_scores")
    table_news = ch_db.get("table_news_items", "news_items")
    return client, db_name, config, table_hourly_scores, table_news


# --- Topic 2: decay in code ---

def _decay_weight(hours_ago: float, tau_hours: float, k: float, weight_cap: float) -> float:
    """Logarithmic decay weight: weight_cap at 0, then 1 / (log10(1 + hours_ago/tau) * k), capped."""
    if hours_ago <= 0:
        return weight_cap
    denom = math.log10(1 + hours_ago / tau_hours) * k
    if denom <= 0:
        return weight_cap
    return min(weight_cap, 1.0 / denom)


def _decayed_scores_from_hourly(
    client,
    table_hourly_scores: str,
    config: dict,
    lookback_hours: int = 168,
) -> tuple[list[tuple[str, float, int, datetime]], datetime | None]:
    """
    Query hourly_currency_scores for last lookback_hours, aggregate by (hour_bucket, symbol),
    then apply decay per hour. Returns list of (symbol, decayed_score, article_count, latest_hour)
    and latest_hour (or None if no data).
    """
    decay_cfg = config.get("decay", {})
    tau_minutes = float(decay_cfg.get("tau_minutes", 20))
    k = float(decay_cfg.get("k", 1.8))
    weight_cap = float(decay_cfg.get("weight_cap", 1.0))
    tau_hours = tau_minutes / 60.0

    q = f"""
    SELECT hour_bucket, symbol, sum(sum_score) AS sum_score, sum(article_count) AS article_count
    FROM {table_hourly_scores}
    WHERE hour_bucket >= now() - INTERVAL {lookback_hours} HOUR
    GROUP BY hour_bucket, symbol
    ORDER BY hour_bucket, symbol
    """
    result = client.query(q)
    rows = result.result_rows
    if not rows:
        return [], None

    # Group by symbol: list of (hour_bucket, sum_score, article_count)
    by_symbol: dict[str, list[tuple[datetime, float, int]]] = {}
    all_hours: list[datetime] = []
    for r in rows:
        hour_bucket, symbol, sum_score, article_count = r[0], r[1], r[2], r[3]
        if isinstance(hour_bucket, datetime) and hour_bucket.tzinfo is None:
            hour_bucket = hour_bucket.replace(tzinfo=timezone.utc)
        all_hours.append(hour_bucket)
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append((hour_bucket, sum_score, article_count))
    latest_hour = max(all_hours) if all_hours else None

    now_utc = datetime.now(timezone.utc)
    out: list[tuple[str, float, int, datetime]] = []
    for symbol, hour_rows in by_symbol.items():
        weighted_sum = 0.0
        weight_sum = 0.0
        total_articles = 0
        for hour_bucket, sum_score, article_count in hour_rows:
            if article_count <= 0:
                continue
            avg_score = sum_score / article_count
            hours_ago = (now_utc - hour_bucket).total_seconds() / 3600.0
            weight = _decay_weight(hours_ago, tau_hours, k, weight_cap)
            weighted_sum += avg_score * weight
            weight_sum += weight
            total_articles += article_count
        if weight_sum > 0 and latest_hour:
            decayed = weighted_sum / weight_sum
            out.append((symbol, decayed, total_articles, latest_hour))
    return out, latest_hour


# --- Response models ---


class CurrencyScore(BaseModel):
    symbol: str
    decayed_score: float
    article_count: int
    timestamp: str


class ScoresResponse(BaseModel):
    scores: list[CurrencyScore]


class ArticleScore(BaseModel):
    usd_bias: float | None
    eur_bias: float | None
    jpy_bias: float | None
    gbp_bias: float | None
    risk_sentiment: float | None
    event_risk_score: float | None


class Article(BaseModel):
    id: str
    timestamp: str
    url: str
    summary: str
    symbols: list[str]
    scores: ArticleScore


class ArticlesResponse(BaseModel):
    articles: list[Article]
    count: int


class NewsItemsScores(BaseModel):
    usd: float
    eur: float
    jpy: float
    gbp: float
    article_count: int
    hours: int


# --- Endpoints ---


@app.get("/health")
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/scores", response_model=ScoresResponse)
def get_scores(lookback_hours: int = Query(168, ge=1, le=720)):
    """Decayed scores per currency: hourly scores from MV, decay applied in code."""
    client, _, config, table_hourly_scores, _ = _get_client()
    rows, latest_hour = _decayed_scores_from_hourly(client, table_hourly_scores, config, lookback_hours)
    scores = [
        CurrencyScore(
            symbol=symbol,
            decayed_score=round(decayed_score, 4),
            article_count=article_count,
            timestamp=latest_hour.isoformat() if latest_hour else "",
        )
        for symbol, decayed_score, article_count, _ in rows
    ]
    return ScoresResponse(scores=scores)


@app.get("/scores/{currency}", response_model=CurrencyScore)
def get_score(currency: str, lookback_hours: int = Query(168, ge=1, le=720)):
    """Decayed score for a single currency (USD, EUR, JPY, GBP); decay applied in code."""
    currency = currency.upper()
    if currency not in ("USD", "EUR", "JPY", "GBP"):
        raise HTTPException(400, f"Unknown currency {currency}")
    client, _, config, table_hourly_scores, _ = _get_client()
    rows, latest_hour = _decayed_scores_from_hourly(client, table_hourly_scores, config, lookback_hours)
    for symbol, decayed_score, article_count, _ in rows:
        if symbol == currency:
            return CurrencyScore(
                symbol=symbol,
                decayed_score=round(decayed_score, 4),
                article_count=article_count,
                timestamp=latest_hour.isoformat() if latest_hour else "",
            )
    raise HTTPException(404, f"No hourly scores for {currency}")


@app.get("/scores/news_items/average", response_model=NewsItemsScores)
def get_news_items_average(
    hours: int = Query(24, ge=1, le=168),
):
    """Average bias per currency from news_items over the last N hours."""
    client, _, _, _, table_news = _get_client()
    q = f"""
    SELECT
      round(avg(JSONExtractFloat(scores, 'usd_bias')), 4) AS usd,
      round(avg(JSONExtractFloat(scores, 'eur_bias')), 4) AS eur,
      round(avg(JSONExtractFloat(scores, 'jpy_bias')), 4) AS jpy,
      round(avg(JSONExtractFloat(scores, 'gbp_bias')), 4) AS gbp,
      count() AS cnt
    FROM {table_news}
    WHERE timestamp >= now() - INTERVAL {hours} HOUR
    """
    result = client.query(q)
    rows = result.result_rows
    if not rows or rows[0][4] == 0:
        return NewsItemsScores(usd=0, eur=0, jpy=0, gbp=0, article_count=0, hours=hours)
    r = rows[0]
    return NewsItemsScores(usd=r[0], eur=r[1], jpy=r[2], gbp=r[3], article_count=r[4], hours=hours)


@app.get("/articles", response_model=ArticlesResponse)
def get_articles(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent articles with scores."""
    client, _, _, _, table_news = _get_client()
    q = f"""
    SELECT id, timestamp, url, summary, symbols, scores
    FROM {table_news}
    WHERE timestamp >= now() - INTERVAL {hours} HOUR
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    result = client.query(q)
    rows = result.result_rows
    articles = []
    for r in rows:
        scores_raw = json.loads(r[5]) if r[5] else {}
        scores = ArticleScore(
            usd_bias=scores_raw.get("usd_bias"),
            eur_bias=scores_raw.get("eur_bias"),
            jpy_bias=scores_raw.get("jpy_bias"),
            gbp_bias=scores_raw.get("gbp_bias"),
            risk_sentiment=scores_raw.get("risk_sentiment"),
            event_risk_score=scores_raw.get("event_risk_score"),
        )
        articles.append(
            Article(
                id=r[0],
                timestamp=str(r[1]),
                url=r[2],
                summary=r[3] or "",
                symbols=r[4] or [],
                scores=scores,
            )
        )
    return ArticlesResponse(articles=articles, count=len(articles))
