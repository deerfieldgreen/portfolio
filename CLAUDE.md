# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Public portfolio for **Deerfield Green** — a boutique subscription and agentic AI studio. Contains independent Python projects for AI agent pipelines, ML systems, and backtesting tools targeting FX/financial markets. All projects are part of the "Cervid" quantitative trading platform.

## Projects

| Project | Stack | Has Tests |
|---------|-------|-----------|
| `agentic_financial_news_scoring/` | Tavily → LLM (Qwen3/Novita) → ClickHouse, FastAPI | No |
| `langgraph_deep_research/` | LangGraph, Novita AI, Parallel AI Deep Research API | `python test_workflow.py` |
| `economic_calendar_agent/` | LangGraph, FMP API, Redis, Qdrant, ClickHouse | pytest (unit/integration/e2e) |
| `tokyo-vc-agent-swarm/` | LangGraph agent swarm, ClickHouse, FastAPI | pytest (unit/integration/e2e) |
| `data_scientist_agent_swarm_research/` | LangGraph + Argo Workflows, PyTorch, MLflow, Qdrant | CI via GitHub Actions |
| `forex_backtesting_library/` | VectorBT, OANDA, Argo Workflows | No |
| `market_regime_detection/` | HMM (hmmlearn), GARCH (arch), FastAPI, Argo | Validation script |
| `market_session_volume/` | PCA, KMeans, ARIMA, Isolation Forest, MLflow, Argo | No |
| `financial_news_agent/` | Earlier news pipeline with Docker Compose | No |

## Common Commands

### Projects with pytest (`economic_calendar_agent`, `tokyo-vc-agent-swarm`)
```bash
cd <project>
pip install -e ".[dev]"
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v
pytest --cov=<package_name> --cov-report=html
```

### `langgraph_deep_research`
```bash
pip install -r requirements.txt
python main.py "your topic"           # streaming mode
python main.py --mock "your topic"    # fast iteration, no API calls
python test_workflow.py               # full test suite, no API keys needed
```

### Other projects
```bash
pip install -r requirements.txt   # or: pip install -e ".[dev]"
doppler run --project <project> --config dev -- python main.py
```

Each project has its own `README.md` with full command reference including Docker, Argo, and FastAPI invocations.

## Architecture Patterns

**Secrets management:** Environment variables only, managed via Doppler (`doppler run --project <name> --config dev/prd -- <cmd>`). No `.env` files committed. `config.yaml` files hold non-secret parameters only. In Docker, full YAML config is passed as the `CONFIG_YAML` env var.

**ClickHouse as time-series store:** All projects write to ClickHouse. Schema pattern: `MergeTree` tables partitioned by `toYYYYMM(timestamp)`, ordered by `(pair, timeframe, timestamp)`. Always use parameterized queries.

**LangGraph orchestration:** `TypedDict` state → node functions → `add_edge`/`add_conditional_edges` → `workflow.compile()` → `graph.invoke(initial_state)`.

**LLM calls via Novita AI (OpenAI-compatible):**
```python
client = openai.OpenAI(base_url="https://api.novita.ai/v3/openai", api_key=NOVITA_API_KEY)
```
Models: `Qwen3-32b-fp8`, `Qwen3-max`, `Qwen3.5-397B-A22B-Instruct-FP8`. Reasoning model responses require stripping `<think>...</think>` tags. JSON extraction: strip `<think>` → try ` ```json``` ` blocks → fall back to first `{...}` brace match.

**UUID5 deduplication (news scoring):** Article IDs are `uuid.uuid5(uuid.NAMESPACE_URL, url)` for deterministic ClickHouse duplicate checks.

**MLflow tracking** (`market_session_volume`, `market_regime_detection`): Models logged, registered, and promoted to Production based on threshold validation.

**Argo Workflows** (`forex_backtesting_library`, `market_regime_detection`, `market_session_volume`, `data_scientist_agent_swarm_research`): Kubernetes pipelines with retry/backoff, shared PVC workspaces, per-step resource limits. Templates in `argos/`.

**Logging convention:**
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
```

**Pydantic v2** for config and FastAPI response models. Pure Python for core math (correlation, surprise, decay calculations).
