# News Scoring Pipeline

Cron-style pipeline: fetch news (Tavily), score with Qwen3 (Novita), store in ClickHouse. All **secrets come from environment variables only**; `config.yaml` contains no secrets and is not used to load API keys or DB credentials.

## Files

| File | Purpose |
|------|---------|
| `config.yaml` | Non-secret config (symbols, queries, decay params, table names). |
| `news_domains.json` | Format reference for allowed news domains (real list stored in Doppler as `NEWS_DOMAINS`). |
| `env.example` | Required env var names; copy to `.env` and set values (do not commit). |
| `scoring_pipeline.py` | Main pipeline: fetch → score → insert. |
| `entrypoint.sh` | Container entry: run once or loop every `CRON_INTERVAL_MINUTES`. |
| `scripts/init_clickhouse.sh` | Create ClickHouse user, DB, `news_items`, `snapshots`. |
| `scripts/01_create_user_database.sql` | User/database (password from env via `envsubst`). |
| `scripts/02_create_tables.sql` | Tables for news items and snapshots. |
| `Dockerfile` | Image for the pipeline. |
| `docker-compose.yml` | Local run: news_agent + ClickHouse. |

## Required environment variables (secrets)

Set these in `.env` or export before run. **Do not put them in config.yaml.**

- `TAVILY_API_KEY` – Tavily search API
- `NOVITA_API_KEY` – Novita (Qwen3) API
- `CLICKHOUSE_HOST` – e.g. `localhost` or `clickhouse` (in compose)
- `CLICKHOUSE_PORT` – e.g. `8123` (or `8124` for local compose)
- `CLICKHOUSE_USERNAME` – e.g. `news_agent`
- `CLICKHOUSE_PASSWORD` – same value used when running `init_clickhouse.sh`
- `CLICKHOUSE_DATABASE` – e.g. `news_agent`

Optional:

- `NEWS_DOMAINS` – JSON for allowed domains. **Source from Doppler.** Accepted: a JSON array, or an object with category keys (e.g. `major_wires_and_financial_media`, `central_banks_and_official`) and optional `exclude_domains`. See `news_domains.json`. Push with: `cat news_domains.json | doppler secrets set NEWS_DOMAINS` (do not use `doppler secrets upload`—that flattens keys and fails). If unset, Tavily returns results from any domain.
- `CONFIG_PATH` – path to `config.yaml` (default in container: `/app/config.yaml`)
- `CRON_INTERVAL_MINUTES` – if set, run pipeline in a loop every N minutes; otherwise run once and exit
- `MAX_QUERIES_PER_CYCLE` – if set, limit to N search queries per cycle (e.g. `3`); unset = all 14 queries

## Docker

### Build

```bash
cd src/news_agent
docker compose build
```

### Local ClickHouse + init

Compose exposes ClickHouse on **port 8124** (HTTP) so it doesn’t clash with other stacks on 8123.

```bash
cd src/news_agent
cp env.example .env
# Edit .env: set TAVILY_API_KEY, NOVITA_API_KEY, CLICKHOUSE_PASSWORD (and optionally CLICKHOUSE_USERNAME=news_agent)

docker compose up -d clickhouse
# Wait for healthy, then create user/DB/tables (uses CLICKHOUSE_PASSWORD from env):
export CLICKHOUSE_PASSWORD='your_password'
./scripts/init_clickhouse.sh
```

### Run pipeline (one shot)

```bash
docker compose run --rm news_agent
```

Secrets are taken from `.env`; compose sets `CLICKHOUSE_HOST=clickhouse`, `CLICKHOUSE_PORT=8123` for the app.

### Run as cron loop (e.g. every 15 minutes)

```bash
docker compose run --rm -e CRON_INTERVAL_MINUTES=15 news_agent
```

Or in `.env`: `CRON_INTERVAL_MINUTES=15`, then `docker compose run --rm news_agent`.

### Run image elsewhere

Build and run the image with env vars set (e.g. orchestrator secrets, or `--env-file .env`):

```bash
docker build -t news_agent .
docker run --rm \
  -e TAVILY_API_KEY -e NOVITA_API_KEY \
  -e CLICKHOUSE_HOST -e CLICKHOUSE_PORT -e CLICKHOUSE_USERNAME -e CLICKHOUSE_PASSWORD -e CLICKHOUSE_DATABASE \
  news_agent
```

## Non-Docker run

```bash
cd src/news_agent
pip install -r requirements.txt
cp env.example .env
# Edit .env with real values
source .env   # or export each var
python3 main.py
```

## Reporting API (FastAPI)

Serve scores and articles over HTTP:

```bash
./doppler/run_api.sh
# or: doppler run --project tavily_news_agent --config dev -- uvicorn api:app --host 0.0.0.0 --port 8000
```

Endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `GET /scores` | Latest decayed scores for all currencies (snapshots) |
| `GET /scores/{currency}` | Latest score for USD, EUR, JPY, or GBP |
| `GET /scores/news_items/average?hours=24` | Average bias from raw articles |
| `GET /articles?hours=24&limit=20` | Recent articles with scores |

Interactive docs: http://localhost:8000/docs

## Design

See `design.md` for architecture, decay formula, and prompt details.

---

## Open questions (for you)

1. **Decay / snapshot**  
   Do you want the container to also **write snapshot rows** (decayed aggregates per symbol) after each cycle, or will a separate job/query compute snapshots from `news_items`? Right now the pipeline only inserts into `news_items`.

2. **Tavily “days”**  
   Config has `tavily.days: 7`. For the initial 7-day backfill, do you want a dedicated **backfill mode** (e.g. `BACKFILL_DAYS=7` and larger batches) or is “recent only” per run enough?

3. **Cron vs one-shot**  
   In production, do you prefer this container to **loop internally** (`CRON_INTERVAL_MINUTES`) or to be run **once per run** by an external scheduler (e.g. Kubernetes CronJob, system cron) with no loop?

4. **ClickHouse init**  
   For production, will ClickHouse be **pre-provisioned** (user/DB/tables created elsewhere), or should we document a one-off init job that runs `scripts/init_clickhouse.sh` (or equivalent) with the same `CLICKHOUSE_PASSWORD`?

5. **Config mount**  
   Do you want to **mount** `config.yaml` from the host in production (e.g. `-v /path/to/config.yaml:/app/config.yaml`) so you can change parameters without rebuilding the image?
