# Economic Calendar Agent

LangGraph-based economic calendar analysis agent for FX trading. Provides real-time correlation analysis combining relevance matrices, surprise factors, and time-decay models.

## Features

- **Multi-layer Correlation Analysis**
  - Static relevance matrix (Andersen et al. 2003)
  - Z-score surprise calculation (ECB Working Paper methodology)
  - Two-component exponential time decay (Evans & Lyons 2005)
  - Composite scoring: Relevance × Impact × Surprise × Decay

- **Data Pipeline**
  - Financial Modeling Prep (FMP) API integration
  - Multi-layer caching (L1 in-memory + L2 Redis)
  - Adaptive TTL based on event proximity
  - Circuit breaker for resilience

- **LangGraph Agent**
  - Economic calendar tool (primary)
  - Stub nodes for technical, sentiment, risk, execution
  - LLM-based orchestration and routing

- **Storage**
  - ClickHouse: Time-series event storage, aggregations, historical stats
  - Qdrant: Semantic search for similar historical scenarios (Phase 4)
  - Redis: Distributed caching layer

## Directory Structure

```
economic_calendar_agent/
├── src/economic_calendar_agent/
│   ├── config.py                   # Pydantic settings
│   ├── models/                     # Pydantic schemas & domain models
│   ├── correlation/                # Core math: relevance, surprise, decay, scorer
│   ├── data/                       # FMP client, ClickHouse, Redis, Qdrant
│   ├── agent/                      # LangGraph StateGraph & nodes
│   ├── pipeline/                   # Argo pipeline steps
│   └── sql/                        # ClickHouse migrations
├── tests/                          # Unit, integration, e2e tests
├── scripts/                        # Backfill, calibration scripts
├── argo/                           # Argo CronWorkflow YAML
├── pyproject.toml                  # Dependencies
├── Dockerfile                      # Container image
└── docker-compose.yml              # Local dev environment
```

## Quick Start

### Local Development

1. **Install dependencies**:
   ```bash
   cd argo_pipelines/economic_calendar_agent
   pip install -e ".[dev]"
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and connection strings
   ```

3. **Start local services**:
   ```bash
   docker-compose up -d  # ClickHouse, Redis, Qdrant
   ```

4. **Run the agent**:
   ```bash
   # With default pairs from config
   python -m economic_calendar_agent.agent_main
   
   # With specific pairs
   python -m economic_calendar_agent.agent_main --pairs USDJPY EURUSD
   
   # JSON output
   python -m economic_calendar_agent.agent_main --output json
   ```

5. **Run tests**:
   ```bash
   # Unit tests
   pytest tests/unit/ -v
   
   # E2E agent tests
   pytest tests/e2e/ -v
   ```

### Core Modules

**Correlation Engine** (Phase 1 — Complete):
```python
from economic_calendar_agent.correlation import event_scorer
from economic_calendar_agent.models.events import EconomicEvent
from economic_calendar_agent.models.schemas import ImpactLevel

# Create event
event = EconomicEvent(
    event_id="nfp-2025-02",
    event_name="Non-Farm Payrolls",
    event_type="NFP",
    country="US",
    currency="USD",
    event_datetime=datetime.now(timezone.utc),
    impact=ImpactLevel.HIGH,
    actual=250000,
    estimate=200000,
    previous=180000,
)

# Score across pairs
scored = event_scorer.score_event(
    event=event,
    pairs=["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"],
    historical_std=20000.0,
)

# Get composite scores
print(scored.composite_scores)  # {"USDJPY": 0.85, "EURUSD": 0.78, ...}
print(scored.surprise_zscore)   # 2.5 (large positive surprise)
```

**FMP Client**:
```python
from economic_calendar_agent.data.fmp_client import FMPClient
from economic_calendar_agent.config import get_settings

settings = get_settings()
client = FMPClient(settings)

# Fetch upcoming events
events = await client.fetch_upcoming_events(hours_ahead=48)
```

**LangGraph Agent**:
```python
from economic_calendar_agent.agent.graph import build_graph

# Build and invoke agent
graph = build_graph()

initial_state = {
    "messages": [],
    "economic_context": None,
    "technical_signals": None,
    "sentiment_scores": None,
    "risk_assessment": None,
    "target_pairs": ["USDJPY", "EURUSD"],
    "current_positions": [],
    "next_action": None,
    "error": None,
}

final_state = await graph.ainvoke(initial_state)

# Access economic context
if final_state.get("economic_context"):
    print(final_state["economic_context"].summary)
```

## Configuration

All settings managed via environment variables (Doppler in production):

```bash
# FMP API
FMP_API_KEY=your_key_here
FMP_BASE_URL=https://financialmodelingprep.com/api/v3
FMP_RATE_LIMIT_PER_MIN=750

# ClickHouse
CH_HOST=localhost
CH_PORT=8123
CH_DATABASE=fx_economic
CH_USER=default
CH_PASSWORD=

# Redis
REDIS_URL=redis://localhost:6379/0

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=economic_events

# LLM
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_openai_key
LLM_TEMPERATURE=0.1

# Trading Pairs
TARGET_PAIRS=USDJPY,EURUSD,GBPUSD,AUDUSD
```

## Testing

```bash
# Unit tests (correlation math)
pytest tests/unit/ -v

# Integration tests (API clients, ClickHouse)
pytest tests/integration/ -v

# E2E tests (full agent graph)
pytest tests/e2e/ -v

# With coverage
pytest --cov=economic_calendar_agent --cov-report=html
```

## Implementation Phases

- **Phase 1** ✅: Core math (relevance, surprise, decay) + FMP client
- **Phase 2** 🚧: LangGraph agent with economic tool node
- **Phase 3** 📅: ClickHouse storage + Argo pipeline
- **Phase 4** 📅: Qdrant semantic search
- **Phase 5** 📅: ML-driven calibration

## Key Design Decisions

1. **Pure Python Correlation Module**: No external dependencies for core math — fast, testable, portable
2. **ClickHouse as Source of Truth**: Decay params and relevance scores stored in DB, updatable without code changes
3. **Event Scorer as Integration Point**: Single function (`score_event`) orchestrates all correlation logic
4. **Adaptive TTL Caching**: TTL varies by event proximity (60s for imminent, 3600s for distant)
5. **Circuit Breaker Pattern**: Protects against FMP API cascading failures

## References

- Andersen et al. (2003): "The Distribution of Exchange Rate Volatility"
- ECB Working Paper 1150 (2010): "Surprise Index Methodology"
- Evans & Lyons (2005): "Meese-Rogoff Redux: Micro-Based Exchange Rate Forecasting"

## License

Proprietary — Cervid Trading Platform
