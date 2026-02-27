# Copilot Instructions

## Repository Overview

This is a public portfolio for **Deerfield Green**, showcasing AI agent pipelines, ML systems, and backtesting tools built around the "Cervid" quantitative trading platform. All projects are Python-only and target FX/financial markets.

| Project | Purpose |
|---|---|
| `agentic_financial_news_scoring/` | Production FX news pipeline: Tavily fetch → LLM score → ClickHouse storage, FastAPI exposure |
| `financial_news_agent/` | Earlier version of the news scoring pipeline with Docker Compose setup |
| `langgraph_deep_research/` | LangGraph workflow: generates research questions → Parallel AI deep research → streaming synthesis |
| `economic_calendar_agent/` | LangGraph agent analyzing FX economic calendar events with multi-layer caching and academic correlation models |
| `forex_backtesting_library/` | VectorBT grid-search backtesting (4 strategy types) on OANDA data, runs on Argo Workflows |
| `market_regime_detection/` | HMM + GARCH 3-state regime detector (bull/bear/neutral) with FastAPI and Argo pipeline |
| `market_session_volume/` | PCA + KMeans + ARIMA + Isolation Forest session volume analysis; MLflow tracking; full Argo DAG |

## Commands

### `economic_calendar_agent` (only project with a test suite)
```bash
pip install -e ".[dev]"
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
pytest --cov=economic_calendar_agent --cov-report=html
```

### `langgraph_deep_research`
```bash
pip install -r requirements.txt
python main.py "your topic"          # streaming
python main.py --mock "your topic"   # fast iteration, skips Parallel AI
python test_workflow.py              # full test suite, no API keys needed
```

### Other projects (per-project)
```bash
pip install -r requirements.txt   # or: pip install -e ".[dev]"
# Secrets via Doppler:
doppler run --project <project> --config dev -- python main.py
```

Each project's `README.md` has the full command reference including Docker, Argo, and FastAPI invocations.

## Architecture Patterns

### Secrets — environment-only, always
API keys, DB credentials, and passwords come exclusively from environment variables or Doppler. No `.env` files are committed. `config.yaml` files contain only non-secret parameters. When working in Docker, the full YAML config is passed as the `CONFIG_YAML` env var string (no file mount).

### Doppler for secrets management
All projects use `doppler run --project <name> --config dev/prd -- <cmd>`. Kubernetes secrets are synced from Doppler.

### ClickHouse as universal time-series store
Every project writes time-series results to ClickHouse. Schema pattern: `MergeTree` tables partitioned by `toYYYYMM(timestamp)`, ordered by `(pair, timeframe, timestamp)`. Materialized Views handle aggregations. Always use parameterized queries.

### LangGraph for agentic orchestration (`economic_calendar_agent`, `langgraph_deep_research`)
Pattern: define `TypedDict` state → add node functions → wire edges with `add_edge`/`add_conditional_edges` → `workflow.compile()` → `graph.invoke(initial_state)`.

### LLM calls via Novita AI (OpenAI-compatible SDK)
```python
client = openai.OpenAI(
    base_url="https://api.novita.ai/v3/openai",
    api_key=NOVITA_API_KEY
)
```
Models used: `Qwen3-32b-fp8`, `Qwen3-max`, `Qwen3.5-397B-A22B-Instruct-FP8`.  
Reasoning model responses require stripping `<think>...</think>` tags before parsing.  
JSON extraction pipeline: strip `<think>` → try ` ```json ``` ` blocks → fall back to first `{...}` brace match.

### Log-decay score aggregation (news scoring projects)
```
weight = min(weight_cap, 1 / (log10(1 + hours_ago / tau) * k))
```
Applied per hourly bucket. Parameters (`tau_minutes`, `k`, `weight_cap`) are configurable in `config.yaml`.

### UUID5 deduplication (news scoring)
Article IDs are `uuid.uuid5(uuid.NAMESPACE_URL, url)` — deterministic, enabling ClickHouse duplicate checks before insertion.

### MLflow experiment tracking (`market_session_volume`, `market_regime_detection`)
Models are logged, registered (`mlflow.register_model`), and promoted to Production based on threshold validation (e.g., MAE ≤ 50000, precision ≥ 0.65).

### Argo Workflows for production pipelines
`forex_backtesting_library`, `market_regime_detection`, `market_session_volume` use Argo on Kubernetes with retry/exponential-backoff, shared PVC workspaces, and per-step resource limits. Workflow templates live in `argos/`.

### Logging convention
All pipelines use:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
```
`market_session_volume` uses a dedicated `logging_config.py` with file output.

### Pydantic v2
`economic_calendar_agent` uses `pydantic>=2.0` and `pydantic-settings` for config and FastAPI response models throughout.

### Pure Python for core math
`economic_calendar_agent` keeps correlation, surprise, and decay calculations in pure Python with no external dependencies. `event_scorer.score_event()` is the single integration point for all correlation logic.
