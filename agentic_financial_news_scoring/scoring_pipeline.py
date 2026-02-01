#!/usr/bin/env python3
"""
News scoring pipeline: fetch (Tavily), score (Qwen3/Novita), store (ClickHouse).
All secrets and config from environment variables only. Config from CONFIG_YAML env.
"""

import os
import re
import sys
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

import yaml
import clickhouse_connect
from openai import OpenAI
from tavily import TavilyClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config from CONFIG_YAML env (YAML string)."""
    env_yaml = os.environ.get("CONFIG_YAML", "").strip()
    if not env_yaml:
        logger.error("CONFIG_YAML env is required.")
        sys.exit(1)
    config = yaml.safe_load(env_yaml)
    logger.info("Config loaded: %d search_queries, %s symbols", len(config.get("search_queries", [])), config.get("symbols"))
    return config


def load_prompt_template(config: dict, base_dir: str | Path) -> str:
    """Load prompt YAML and return template string with {news_text}, {timestamp}, {source}."""
    path = config.get("prompt_path") or "NEWS_SCORE_V1.yaml"
    if not os.path.isabs(path):
        path = Path(base_dir) / path
    with open(path, "r") as f:
        prompt_cfg = yaml.safe_load(f)
    return (prompt_cfg.get("template") or "").strip()


def _extract_json_from_llm_text(text: str) -> str | None:
    """Extract JSON from LLM output. Handles ```json blocks, <think> tags, and raw {...}."""
    if not text or not text.strip():
        return None
    text = text.strip()
    # Remove <think>...</think> blocks (reasoning models)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = text.strip()
    # Prefer ```json ... ``` block
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_block:
        return json_block.group(1).strip() or None
    # Fall back to first {...} object
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0).strip() or None
    return text if text.startswith("{") else None


_G8_CURRENCIES = frozenset({"USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "NZD"})


def _get_max_queries_per_cycle() -> int | None:
    """Parse MAX_QUERIES_PER_CYCLE env. Returns None = all queries, or positive int limit."""
    raw = os.environ.get("MAX_QUERIES_PER_CYCLE", "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
        return max(1, n) if n > 0 else None
    except ValueError:
        return None


_INCLUDE_KEYS = (
    "major_wires_and_financial_media",
    "central_banks_and_official",
    "fx_and_macro_aggregators",
    "japan_and_jpy_relevant_media",
    "other_regional_outlets",
    "financial_news_domains",  # legacy
)


def get_news_domains_from_env() -> list[str]:
    """Parse optional NEWS_DOMAINS from env. Source from Doppler.
    Accepts:
      - JSON array of domain strings
      - Object with category keys (arrays) and optional exclude_domains (array).
        Include keys: major_wires_and_financial_media, central_banks_and_official,
        fx_and_macro_aggregators, japan_and_jpy_relevant_media, other_regional_outlets,
        financial_news_domains (legacy).
        exclude_domains are removed from the final list.
    """
    raw = os.environ.get("NEWS_DOMAINS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Invalid NEWS_DOMAINS JSON, ignoring: %s", e)
        return []
    if isinstance(data, list):
        domains = data
        exclude: list[str] = []
    elif isinstance(data, dict):
        seen: set[str] = set()
        domains = []
        for key in _INCLUDE_KEYS:
            arr = data.get(key)
            if isinstance(arr, list):
                for d in arr:
                    s = str(d).strip()
                    if s and s not in seen:
                        seen.add(s)
                        domains.append(s)
        exclude = [str(d).strip() for d in data.get("exclude_domains", []) if d and str(d).strip()]
    else:
        return []
    result = [d for d in domains if d and d not in exclude][:300]
    return result


def get_secrets_from_env() -> dict:
    """Required secrets; no file loading. Raises if any missing."""
    required = {
        "TAVILY_API_KEY": os.environ.get("TAVILY_API_KEY"),
        "NOVITA_API_KEY": os.environ.get("NOVITA_API_KEY"),
        "CLICKHOUSE_HOST": os.environ.get("CLICKHOUSE_HOST"),
        "CLICKHOUSE_PORT": os.environ.get("CLICKHOUSE_PORT"),
        "CLICKHOUSE_USERNAME": os.environ.get("CLICKHOUSE_USERNAME"),
        "CLICKHOUSE_PASSWORD": os.environ.get("CLICKHOUSE_PASSWORD"),
        "CLICKHOUSE_DATABASE": os.environ.get("CLICKHOUSE_DATABASE"),
    }
    missing = [k for k, v in required.items() if not (v and str(v).strip())]
    if missing:
        raise SystemExit(f"Missing required env: {', '.join(missing)}. Do not load secrets from file.")
    return {k: v.strip() for k, v in required.items() if v}


def run_one_cycle(config: dict, secrets: dict, config_dir: Path) -> None:
    ch_db = config.get("clickhouse", {})
    db_name = ch_db.get("database", "news_agent")
    table_news = ch_db.get("table_news_items", "news_items")
    queries = config.get("search_queries", ["USDJPY news", "EURUSD news"])
    tavily_cfg = config.get("tavily", {})
    novita_cfg = config.get("novita", {})

    prompt_template = load_prompt_template(config, config_dir)
    logger.info("Prompt template loaded from %s", config.get("prompt_path", "NEWS_SCORE_V1.yaml"))

    client_tavily = TavilyClient(api_key=secrets["TAVILY_API_KEY"])
    client_llm = OpenAI(
        base_url=novita_cfg.get("base_url", "https://api.novita.ai/v3/openai"),
        api_key=secrets["NOVITA_API_KEY"],
    )
    secure = (os.environ.get("CLICKHOUSE_SECURE", "").strip().lower() in ("true", "1", "yes"))
    ch_client = clickhouse_connect.get_client(
        host=secrets["CLICKHOUSE_HOST"],
        port=int(secrets["CLICKHOUSE_PORT"]),
        username=secrets["CLICKHOUSE_USERNAME"],
        password=secrets["CLICKHOUSE_PASSWORD"],
        database=db_name,
        secure=secure,
    )
    logger.info("ClickHouse connected: %s:%s/%s (table=%s)", secrets["CLICKHOUSE_HOST"], secrets["CLICKHOUSE_PORT"], db_name, table_news)

    include_domains = get_news_domains_from_env()
    if include_domains:
        logger.info("Tavily include_domains: %s", include_domains[:10])

    def _date_range(hours: int) -> tuple[str, str]:
        """Compute start_date and end_date (YYYY-MM-DD) for past N hours."""
        now_utc = datetime.now(timezone.utc)
        start = now_utc - timedelta(hours=hours)
        return start.strftime("%Y-%m-%d"), now_utc.strftime("%Y-%m-%d")

    inserted = 0
    skipped_duplicate = 0
    skipped_no_content = 0
    skipped_no_primary_currency = 0
    llm_errors = 0

    max_queries = _get_max_queries_per_cycle()
    queries_to_run = queries[:max_queries] if max_queries else queries
    logger.info("Running %d of %d queries (MAX_QUERIES_PER_CYCLE=%s)", len(queries_to_run), len(queries), os.environ.get("MAX_QUERIES_PER_CYCLE") or "all")

    for query in queries_to_run:
        exclude_domains = tavily_cfg.get("exclude_domains") or []
        logger.info("Tavily search: query=%r max_results=%d include_domains=%d exclude_domains=%d", query, min(tavily_cfg.get("max_results", 30), 20), len(include_domains), len(exclude_domains))
        search_kw: dict = {
            "query": query,
            "search_depth": tavily_cfg.get("search_depth", "advanced"),
            "max_results": min(tavily_cfg.get("max_results", 30), 20),  # API max 20
            "include_answer": tavily_cfg.get("include_answer", False),
            "include_raw_content": tavily_cfg.get("include_raw_content", True),
            "auto_parameters": tavily_cfg.get("auto_parameters", False),
        }
        hours_cfg = tavily_cfg.get("hours")
        if hours_cfg is None and tavily_cfg.get("days") is not None:
            hours_cfg = int(tavily_cfg["days"]) * 24  # backward compat
        if hours_cfg is not None:
            start_date, end_date = _date_range(int(hours_cfg))
            search_kw["start_date"] = start_date
            search_kw["end_date"] = end_date
            search_kw["days"] = None  # SDK defaults to 7; must unset when using start_date/end_date
            search_kw["time_range"] = None
            logger.info("Tavily date range: %s to %s (past %dh)", start_date, end_date, int(hours_cfg))
        if include_domains:
            search_kw["include_domains"] = include_domains
        if exclude_domains:
            search_kw["exclude_domains"] = exclude_domains
        response = client_tavily.search(**search_kw)
        # Tavily SDK returns a dict; support both dict and object for robustness.
        results = (
            response.get("results", [])
            if isinstance(response, dict)
            else (getattr(response, "results", None) or [])
        )
        logger.info("Tavily returned %d results for query=%r", len(results), query)
        if not results:
            logger.info("No Tavily results for query=%s", query)
            continue

        def _get(r: object, key: str, default: str = "") -> str:
            if isinstance(r, dict):
                return (r.get(key) or default) or ""
            return (getattr(r, key, None) or default) or ""

        max_per_query = min(config.get("batch_size", 50), len(results))
        to_process = results[:max_per_query]
        for i, r in enumerate(to_process):
            url = _get(r, "url")
            title = _get(r, "title") or "(no title)"
            raw = _get(r, "raw_content") or _get(r, "content")
            if not raw:
                skipped_no_content += 1
                logger.info("[%d/%d] Skip (no raw_content): url=%s title=%s", i + 1, len(to_process), url[:80], title[:50])
                continue
            article_id = uuid.uuid5(uuid.NAMESPACE_URL, url)
            logger.info("[%d/%d] Process: id=%s url=%s raw_len=%d", i + 1, len(to_process), article_id, url[:60], len(raw))

            existing = ch_client.query(
                f"SELECT 1 FROM {table_news} WHERE id = {{id:String}} LIMIT 1",
                parameters={"id": str(article_id)},
            )
            if existing.result_rows:
                skipped_duplicate += 1
                logger.info("Skip duplicate id=%s url=%s", article_id, url[:60])
                continue

            ts_iso = datetime.now(timezone.utc).isoformat()
            source = _get(r, "title") or url or "unknown"
            news_text = (raw[:8000] + "..." if len(raw) > 8000 else raw)
            prompt = prompt_template.format(
                news_text=news_text,
                timestamp=ts_iso,
                source=source,
            )
            try:
                logger.info("LLM scoring: model=%s prompt_len=%d", novita_cfg.get("model", "qwen/qwen3-32b-fp8"), len(prompt))
                resp = client_llm.chat.completions.create(
                    model=novita_cfg.get("model", "qwen/qwen3-32b-fp8"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=novita_cfg.get("temperature", 0.2),
                    max_tokens=novita_cfg.get("max_tokens", 512),
                )
                msg = resp.choices[0].message

                def _message_text(raw: str | list | dict | None) -> str:
                    if raw is None:
                        return ""
                    if isinstance(raw, str):
                        return raw.strip()
                    if isinstance(raw, dict):
                        return (raw.get("text") or getattr(raw, "text", None) or "").strip()
                    if isinstance(raw, list):
                        out = []
                        for part in raw:
                            if isinstance(part, dict) and part.get("type") == "text":
                                out.append((part.get("text") or "").strip())
                            elif hasattr(part, "type") and getattr(part, "type", None) == "text":
                                out.append((getattr(part, "text", None) or "").strip())
                        return " ".join(out).strip()
                    return ""

                content_text = _message_text(msg.content)
                reasoning_text = _message_text(getattr(msg, "reasoning_content", None))
                combined = f"{reasoning_text}\n\n{content_text}".strip() if reasoning_text else content_text
                if not combined:
                    llm_errors += 1
                    logger.warning("LLM returned empty content for %s url=%s", article_id, url[:60])
                    scores = {"summary": "", "relevance_score": 0}
                else:
                    json_str = _extract_json_from_llm_text(combined)
                    if not json_str:
                        llm_errors += 1
                        logger.warning("LLM response has no JSON for %s url=%s content_preview=%s", article_id, url[:60], repr(combined[:300]))
                        scores = {"summary": "", "relevance_score": 0}
                    else:
                        scores = json.loads(json_str)
            except json.JSONDecodeError as e:
                llm_errors += 1
                logger.warning("LLM JSON parse failed for %s url=%s: %s content_preview=%s", article_id, url[:60], e, repr(combined[:400]))
                scores = {"summary": "", "relevance_score": 0}
            except Exception as e:
                llm_errors += 1
                logger.warning("LLM request failed for %s url=%s: %s", article_id, url[:60], e)
                scores = {"summary": "", "relevance_score": 0}

            primary_currency = (scores.get("primary_currency") or "").strip().upper()
            is_valid_primary = (
                primary_currency in _G8_CURRENCIES
                or any(ccy in primary_currency for ccy in _G8_CURRENCIES)
            )
            if not is_valid_primary:
                skipped_no_primary_currency += 1
                logger.info("Skip (no primary currency): id=%s url=%s primary_currency=%r", article_id, url[:60], primary_currency or "(missing)")
                continue

            def _f(key: str) -> float:
                v = scores.get(key)
                if v is None:
                    return 0.0
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0

            summary = scores.get("summary", "") or ""
            symbols = list(scores.get("affected_pairs", [])) or list(config.get("symbols", ["USDJPY", "EURUSD", "USD"]))
            ts = datetime.now(timezone.utc).replace(tzinfo=None)

            ch_client.insert(
                table_news,
                [[
                    str(article_id),
                    ts,
                    symbols,
                    url,
                    raw[:50000],
                    json.dumps(scores),
                    summary,
                    _f("relevance_score"),
                    _f("volatility_impact"),
                    _f("timeliness_score"),
                    _f("confidence"),
                    primary_currency[:16] if primary_currency else "",
                    _f("bearish"),
                    _f("bullish"),
                    _f("neutral"),
                ]],
                column_names=[
                    "id", "timestamp", "symbols", "url", "raw_text", "scores", "summary",
                    "relevance_score", "volatility_impact", "timeliness", "confidence", "primary_ccy",
                    "bearish_prob", "bullish_prob", "neutral_prob",
                ],
            )
            inserted += 1
            logger.info("Inserted id=%s symbols=%s summary=%s", article_id, symbols, (summary[:80] + "..." if len(summary) > 80 else summary))

    ch_client.close()
    logger.info("Cycle summary: inserted=%d skipped_duplicate=%d skipped_no_content=%d skipped_no_primary_currency=%d llm_errors=%d", inserted, skipped_duplicate, skipped_no_content, skipped_no_primary_currency, llm_errors)


def main() -> None:
    logger.info("news_agent pipeline starting")
    config = load_config()
    config_dir = Path(__file__).resolve().parent
    secrets = get_secrets_from_env()
    logger.info("Secrets loaded: TAVILY_API_KEY=%s NOVITA_API_KEY=%s CLICKHOUSE=%s", "***" if secrets.get("TAVILY_API_KEY") else "MISSING", "***" if secrets.get("NOVITA_API_KEY") else "MISSING", f"{secrets.get('CLICKHOUSE_HOST')}:{secrets.get('CLICKHOUSE_PORT')}")
    run_one_cycle(config, secrets, config_dir)
    logger.info("Cycle done.")


if __name__ == "__main__":
    main()
