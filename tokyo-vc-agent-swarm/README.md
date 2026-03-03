# Tokyo VC Agent Swarm

A LangGraph-based agent swarm that scores VC deal memos across **7 dimensions** and returns a composite-weighted ranked list. Designed for Tokyo/Japan-focused funds evaluating deal flow.

## Architecture

```
Input deals (JSON)
       │
       ▼
┌──────────────┐
│  initializer │  Normalise deal dicts into SwarmState
└──────┬───────┘
       │
       ▼
┌───────────────────────┐
│  scoring_orchestrator │  asyncio.gather → 7 LLM dimension agents in parallel
│  ┌───────┐ ┌───────┐  │
│  │market │ │ team  │  │  → Novita AI / Qwen3 (tightly constrained JSON prompts)
│  └───────┘ └───────┘  │
│  ┌────────┐ ┌───────┐ │
│  │product │ │traction│ │
│  └────────┘ └───────┘ │
│  ┌────────────┐ ┌────┐ │
│  │syndication │ │risk│ │
│  └────────────┘ └────┘ │
│  ┌──────────┐          │
│  │japan_fit │          │
│  └──────────┘          │
└──────────┬────────────┘
           │
           ▼
┌───────────────────┐
│  composite_ranker │  Weighted sum (risk inverted), sort descending
└──────────┬────────┘
           │
           ▼
┌──────────────────────┐
│  output_formatter    │  Natural-language explanations, RankedDeal list
└──────────┬───────────┘
           │
           ▼
   ClickHouse storage
   FastAPI response
```

## Scoring Dimensions

| Dimension | Weight | Inverted? | Focus |
|---|---|---|---|
| `market` | 1.0 | no | TAM, competition, Japan tailwinds |
| `team` | 1.2 | no | Founders, exits, Japan expertise |
| `product` | 1.0 | no | IP, defensibility, localization moat |
| `traction` | 1.5 | no | ARR/MRR, growth, retention |
| `syndication_fit` | 1.5 | no | Round size, investor mix, CVC interest |
| `risk_regulatory` | 0.8 | **yes** | FEFTA, sector licensing, FX risk |
| `japan_fit` | 1.0 | no | Localization, partnerships, ecosystem |

> **Inversion**: `risk_regulatory` uses `(10 - score)` before weighting so higher risk lowers the composite score.

All weights are configurable in `config.yaml` and overridable per API call.

## Quickstart

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Set secrets

```bash
# Via environment variables:
export NOVITA_API_KEY=your_key
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PASSWORD=your_password

# Or via Doppler:
doppler run --project tokyo-vc-swarm --config dev -- python main.py ...
```

### 3. Score deals from CLI

```bash
# Score from a JSON file (real LLM calls):
python main.py --input deals.json

# Mock mode (stub scores, no LLM, no API key needed):
python main.py --input deals.json --mock

# Top 5 only, skip ClickHouse:
python main.py --input deals.json --mock --top-k 5 --no-clickhouse

# From stdin:
cat deals.json | python main.py --mock
```

**Input format** (`deals.json`):
```json
[
  {
    "deal_id": "deal-001",
    "company": "AlphaAI",
    "sector": "B2B SaaS",
    "stage": "Series A",
    "arr_usd": 2000000,
    "growth_yoy_pct": 180,
    "team_size": 12,
    "japan_customers": true,
    "round_size_usd": 8000000
  }
]
```

### 4. Run the FastAPI server

```bash
uvicorn tokyo_vc_swarm.api:app --reload --host 0.0.0.0 --port 8000
```

**Score deals via API:**
```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "deals": [{"deal_id": "d1", "company": "AlphaAI", "arr_usd": 2000000}],
    "mock": true,
    "persist": false
  }'
```

**Response:**
```json
{
  "run_id": "uuid...",
  "ranked_deals": [
    {
      "rank": 1,
      "deal_id": "d1",
      "composite_score": 7.42,
      "dimensions": {
        "market": {"score": 7.5, "weight": 1.0, "rationale": "..."},
        ...
      },
      "explanation": "Rank #1 (composite 7.42/10): strong traction and syndication fit..."
    }
  ]
}
```

**Get latest rankings:**
```bash
curl "http://localhost:8000/rankings?top_k=5"
```

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/score` | POST | Score and rank deals |
| `/rankings` | GET | Top-K from latest ClickHouse run |

### `POST /score` body

| Field | Type | Default | Description |
|---|---|---|---|
| `deals` | `list` | required | Deal JSON objects |
| `weight_overrides` | `dict` | `null` | Per-dimension weight overrides |
| `mock` | `bool` | `false` | Stub scores (no LLM) |
| `persist` | `bool` | `true` | Write to ClickHouse |

## ClickHouse Schema

```sql
-- deal_scores: one row per (deal, run)
CREATE TABLE vc_swarm.deal_scores (
    deal_id         String,
    run_id          String,
    scored_at       DateTime,
    composite_score Float64,
    rank            UInt32,
    dimensions_json String,   -- JSON blob of all 7 DimensionScore objects
    explanation     String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(scored_at)
ORDER BY (deal_id, scored_at);

-- deal_rankings: one row per (run, rank position)
CREATE TABLE vc_swarm.deal_rankings (
    run_id          String,
    ranked_at       DateTime,
    rank            UInt32,
    deal_id         String,
    composite_score Float64,
    explanation     String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(ranked_at)
ORDER BY (run_id, rank);
```

Tables are created automatically on startup.

## Testing

```bash
# Unit tests (no API key needed):
pytest tests/unit/ -v

# Integration tests (mock mode, no LLM or DB):
pytest tests/integration/ -v

# E2E tests (FastAPI TestClient, mock mode):
pytest tests/e2e/ -v

# Full suite with coverage:
pytest --cov=tokyo_vc_swarm --cov-report=html
```

## Tuning Weights

Edit `config.yaml` to adjust dimension weights per fund strategy:

```yaml
dimensions:
  traction:
    weight: 2.0   # Raise for revenue-stage deals
  team:
    weight: 1.5   # Raise for pre-revenue/deep-tech
  risk_regulatory:
    weight: 1.2   # Raise for regulated sectors (fintech, healthtech)
    invert: true  # Keep inverted
```

Or override per API call:
```json
{"deals": [...], "weight_overrides": {"traction": 2.0, "team": 1.5}}
```

## Stack

- **LangGraph** — graph orchestration
- **Novita AI** (Qwen3) — LLM scoring, OpenAI-compatible SDK
- **ClickHouse** — time-series results storage
- **FastAPI** — API layer
- **Doppler** — secrets management
