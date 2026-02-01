# Agentic Financial News Scoring

Cron-style pipeline that fetches FX news (Tavily), scores articles with Qwen3 (Novita), and stores results in ClickHouse. A FastAPI app exposes decayed currency scores and recent articles.

**Secrets and config:** All API keys and ClickHouse credentials come from **environment variables only**. Config is provided via the `CONFIG_YAML` env var (YAML string); `config.yaml` in the repo is the reference and contains no secrets.

---

## Overview

| Component | Role |
| --------- | ---- |
| **Tavily** | News search (FX-focused queries: USDJPY, EURUSD, central banks, macro). |
| **Novita (Qwen3)** | OpenAI-compatible LLM; scores each article (primary currency, bearish/bullish/neutral, timeliness, volatility). |
| **ClickHouse** | Stores `news_items` and optional hourly/materialized views for scores. |
| **API** | FastAPI: decayed scores per currency, recent articles, optional averages from `news_items`. |

---

## Requirements

- Python 3.11+
- **Required env:** `TAVILY_API_KEY`, `NOVITA_API_KEY`, `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USERNAME`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`, `CONFIG_YAML`
- **Optional env:** `CLICKHOUSE_SECURE` (true/1/yes for TLS), `MAX_QUERIES_PER_CYCLE`, `NEWS_DOMAINS` (JSON), `CRON_INTERVAL_MINUTES`

Config is loaded from `CONFIG_YAML` (the full YAML as a string). Use the repo’s `config.yaml` as the source, e.g.:

```bash
export CONFIG_YAML="$(cat config.yaml)"
```

---

## Quick start

1. **Set secrets and config** (no `.env` in repo; use your own env or Doppler):

   ```bash
   export TAVILY_API_KEY="..."
   export NOVITA_API_KEY="..."
   export CLICKHOUSE_HOST="localhost"   # or your ClickHouse host
   export CLICKHOUSE_PORT="8123"
   export CLICKHOUSE_USERNAME="news_agent"
   export CLICKHOUSE_PASSWORD="..."
   export CLICKHOUSE_DATABASE="news_agent"
   export CONFIG_YAML="$(cat config.yaml)"
   ```

2. **Initialize ClickHouse** (user, database, tables):

   ```bash
   ./scripts/init_clickhouse.sh
   ```

   For remote ClickHouse, set `CLICKHOUSE_HOST` (and optionally `CLICKHOUSE_SECURE`). For local Docker, the script can start `docker compose` and run SQL in the container.

3. **Run one pipeline cycle**:

   ```bash
   python main.py
   ```

4. **Run the API** (scores and articles):

   ```bash
   pip install -r requirements.txt
   uvicorn api:app --host 0.0.0.0 --port 8000
   ```

   With Doppler:

   ```bash
   doppler run --project tavily_news_agent --config dev -- uvicorn api:app --host 0.0.0.0 --port 8000
   ```

---

## Project layout

| Path | Purpose |
| ---- | -------- |
| `config.yaml` | Non-secret config (symbols, Tavily/Novita params, decay, prompt path). Source for `CONFIG_YAML`. |
| `NEWS_SCORE_V1.yaml` | Prompt template for the LLM (`{news_text}`, `{timestamp}`, `{source}`). |
| `scoring_pipeline.py` | Pipeline: load config from env, fetch Tavily, score with Novita, insert into ClickHouse. |
| `main.py` | Entrypoint: runs one cycle. |
| `api.py` | FastAPI: `/health`, `/scores`, `/scores/{currency}`, `/scores/news_items/average`, `/articles`. |
| `scripts/init_clickhouse.sh` | Creates user, DB, and tables; uses `CLICKHOUSE_*` from env. |
| `scripts/01_create_user_database.sql` | User and DB (password via `${CLICKHOUSE_PASSWORD}` substituted by script). |
| `scripts/02_create_tables.sql` | `news_items` (and related) schema. |
| `scripts/03_add_score_columns.sql` | Score columns. |
| `scripts/04_mv_hourly_from_new_columns.sql` | Hourly MV definitions. |
| `scripts/create_mv_hourly_scores.py` | Builds hourly aggregate MV from `news_items`. |
| `scripts/query_news_items.py` | Query `news_items` (scores, summary, optional raw). |
| `scripts/query_currency_score.py` | Query scores from snapshots or `news_items`. |
| `scripts/purge_clickhouse.py` | Truncate tables for testing (`--yes` required). |

---

## API endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Liveness. |
| GET | `/scores` | Decayed scores per currency (from hourly MV + decay in code). Query: `lookback_hours` (default 168). |
| GET | `/scores/{currency}` | Decayed score for one of USD, EUR, JPY, GBP. |
| GET | `/scores/news_items/average` | Average bias from `news_items` over last N hours. Query: `hours`. |
| GET | `/articles` | Recent articles with scores. Query: `hours`, `limit`. |

---

## Docker

Secrets and config are not baked into the image; pass them at run time.

```bash
docker build -t news_agent .
docker run --rm -e TAVILY_API_KEY -e NOVITA_API_KEY \
  -e CLICKHOUSE_HOST -e CLICKHOUSE_PORT -e CLICKHOUSE_USERNAME \
  -e CLICKHOUSE_PASSWORD -e CLICKHOUSE_DATABASE \
  -e CONFIG_YAML="$(cat config.yaml)" \
  news_agent
```

Or use `--env-file` or an orchestrator (e.g. Doppler) to inject env. `.env` is in `.dockerignore` and is not copied into the image.

---

## Scripts (with Doppler)

All scripts expect the same env (or Doppler):

```bash
# One pipeline cycle
doppler run --project tavily_news_agent --config dev -- python main.py

# API
doppler run --project tavily_news_agent --config dev -- uvicorn api:app --host 0.0.0.0 --port 8000

# Query news items
doppler run --project tavily_news_agent --config dev -- python scripts/query_news_items.py --hours 168 --limit 20

# Query currency score (snapshots or news_items)
doppler run --project tavily_news_agent --config dev -- python scripts/query_currency_score.py --currency USD

# Create hourly MV from news_items
doppler run --project tavily_news_agent --config dev -- python scripts/create_mv_hourly_scores.py

# Purge tables (testing)
doppler run --project tavily_news_agent --config dev -- python scripts/purge_clickhouse.py --yes
```

---

## Config (`config.yaml` → `CONFIG_YAML`)

- **symbols** – List of symbols (e.g. USDJPY, EURUSD, USD).
- **search_queries** – Tavily search queries (FX, central banks, macro).
- **tavily** – Search depth, max_results, hours, exclude_domains, etc. API key from `TAVILY_API_KEY`.
- **novita** – Model, temperature, max_tokens, base_url. API key from `NOVITA_API_KEY`.
- **decay** – Log decay for aggregating scores (base, tau_minutes, k, weight_cap, mode, score_field).
- **prompt_path** – Filename for prompt YAML (e.g. `NEWS_SCORE_V1.yaml`).

Optional **clickhouse** section in config can override: `database`, `table_news_items`, `table_hourly_scores`, etc. Defaults: database `news_agent`, table `news_items`, hourly table `hourly_currency_scores`.

---

## Security

- **No secrets in repo.** API keys and DB credentials are read only from the environment.
- **`.env`** is listed in the project’s `.gitignore` (or parent); do not commit `.env`.
- **`.dockerignore`** excludes `.env` so it is never copied into the Docker build context.
