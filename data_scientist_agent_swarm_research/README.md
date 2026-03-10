# AI Swarm Data Scientist — Autonomous FX Prediction Research

An autonomous research system that continuously discovers, trains, evaluates, and promotes FX prediction models. A LangGraph agent swarm (Strategist -> Engineer -> Meta-Learner) generates experiment hypotheses from crawled research papers, submits Argo training workflows via Hera, and promotes winning models through an MLflow registry to hourly serving pipelines.

> **Design doc:** `obsidian/cervid/Designs/AI Swarm Data Scientist/Core Design.md`

---

## Table of Contents

- [System Architecture](#system-architecture)
- [End-to-End Data Flow](#end-to-end-data-flow)
- [Agent Swarm Deep Dive](#agent-swarm-deep-dive)
- [Research Crawler](#research-crawler)
- [Training Pipeline](#training-pipeline)
- [Serving Pipeline](#serving-pipeline)
- [Advanced Validation](#advanced-validation)
- [Use Cases](#use-cases)
- [Database Schema](#database-schema)
- [Infrastructure](#infrastructure)
- [Setup](#setup)
- [Running](#running)
- [Environment Variables](#environment-variables)
- [CI/CD](#cicd)

---

## System Architecture

The system consists of three Argo CronWorkflows operating on different cadences, unified by ClickHouse (analytics), Qdrant (vector memory), MLflow (model registry), and DragonflyDB (state persistence):

```
                        ┌──────────────────────────────────────────────────┐
                        │              WEEKLY: fx-swarm                     │
                        │                                                  │
                        │   ┌────────────┐  ┌────────────┐  ┌───────────┐ │
                        │   │ Strategist │─>│  Engineer  │─>│Meta-Learner│ │
                        │   │  (plan)    │  │  (design)  │  │  (learn)  │ │
                        │   └────────────┘  └────────────┘  └───────────┘ │
                        │        ^   crawl_research -> load_context   |    │
                        │        └────────────────────────────────────┘    │
                        │                     | execute (Hera->Argo)       │
                        └─────────────────────┼────────────────────────────┘
                                              v
┌──────────────────────────────────────────────────────────────────────────┐
│                     MONTHLY: fx-training-monthly                         │
│                                                                          │
│  load-universe -> extract OHLCV -> train (GPU) -> CPCV eval -> promote  │
│                   (walk-forward + Optuna HPO + Deflated Sharpe + PBO)    │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   | MLflow champion alias
                                   v
┌──────────────────────────────────────────────────────────────────────────┐
│                       HOURLY: fx-serving                                 │
│                                                                          │
│  ingest OHLCV -> compute features -> predict -> write ClickHouse        │
│                -> backfill actuals -> aggregate cross-TF -> validate     │
└──────────────────────────────────────────────────────────────────────────┘

External Stores:
  ┌─────────┐  ┌────────────┐  ┌───────────┐  ┌─────────────┐
  │ Qdrant  │  │ ClickHouse │  │  MLflow   │  │ DragonflyDB │
  │ vectors │  │ time-series│  │ registry  │  │ checkpoints │
  └─────────┘  └────────────┘  └───────────┘  └─────────────┘
```

### How the Pieces Fit Together

```
  arXiv / Tavily                Novita AI (Qwen 3.5 397B)
       |                              |
       v                              v
  ┌─────────┐    ┌──────────────────────────────┐
  │Research │    │     LangGraph Swarm Graph     │
  │ Crawler │───>│                               │
  └─────────┘    │  crawl -> context -> plan     │
                 │    -> design -> execute       │
  ┌─────────┐    │    -> evaluate -> learn       │
  │ Qdrant  │<──>│                               │
  │ Memory  │    └──────────┬───────────────────┘
  └─────────┘               |
                    ┌───────v───────┐
                    │  Argo / Hera  │   GPU training pods
                    │  Workflows    │   on Kubernetes
                    └───────┬───────┘
                            |
                    ┌───────v───────┐
                    │    MLflow     │   Model registry
                    │   Registry   │   champion aliases
                    └───────┬───────┘
                            |
                    ┌───────v───────┐
                    │   Serving     │   Hourly predictions
                    │   Pipeline   │   -> ClickHouse
                    └───────────────┘
```

---

## End-to-End Data Flow

### Weekly Swarm Cycle

```
Step 1: CRAWL RESEARCH
  arXiv (7 categories)  ──┐
  Tavily (7 sites)      ──┤──> Dedup (xxhash64)
                           |      |
                           v      v
                    Classify (qwen3-32b) ──> relevance >= 0.4?
                           |                       |
                           | yes                   | no
                           v                       v
                    Chunk + Embed            Log rejection
                    (qwen3-embed-8b)
                           |
                           v
                    Qdrant (fx_research) + ClickHouse (fxs_research_corpus)

Step 2: LOAD CONTEXT
  Query fxs_serving_universe (G10 majors x {H1, H4})
  Fetch champion metrics from MLflow
  Retrieve active ExpeL insights from fxs_insights
  Semantic search relevant research for this cycle

Step 3: PLAN (Strategist Agent)
  Thompson Sampling allocates budget across 6 arms:
    ┌──────────────┬───────────────┬──────────┐
    │ arch_search  │ feature_eng   │ strategy │
    │ ensemble     │ regime        │ refine   │
    └──────────────┴───────────────┴──────────┘
  Generate N experiment specs (batch_size=4)
  Filter: cosine similarity < 0.9 vs past experiments
  Respect active insights (hard constraints)

Step 4: DESIGN (Engineer Agent)
  For each ExperimentSpec:
    Generate PyTorch / sklearn / XGBoost code
    AST sandbox validation (allowlist imports, block os/subprocess/eval)
    Retry once if invalid -> fallback stub if all fail
  Output: experiment_id -> Python code string

Step 5: EXECUTE (Hera Submission)
  Store code to S3 (fx-swarm/cycles/{cycle_id}/{exp_id}/experiment.py)
  Build Argo DAG per experiment:
    extract-data (CPU) -> train (GPU, 1x GPU, 16Gi) -> evaluate (CPU)
  Submit via Hera, poll for completion (4h timeout)

Step 6: EVALUATE (Deterministic)
  Compare candidate DSR vs champion DSR + threshold (0.05)
  Track consecutive_no_improvement counter
  Circuit breaker at 50 consecutive failures

Step 7: LEARN (Meta-Learner Agent)
  Log to fxs_experiments (ClickHouse)
  Upsert embeddings to Qdrant (fx_experiments)
  Extract ExpeL-style insights with confidence scores
  Update Thompson Sampling bandit state (alpha/beta)
  Store insights to fxs_insights

Step 8: LOOP or CIRCUIT BREAK
  If consecutive_no_improvement >= 50 -> Discord alert, stop
  Otherwise -> back to Step 3 with updated bandit state
```

### Monthly Training Pipeline

```
  ┌──────────────┐
  │ Serving      │ Query fxs_serving_universe
  │ Universe     │ (7 pairs x 2 timeframes = 14 combos)
  └──────┬───────┘
         │
         v (per pair/TF)
  ┌──────────────┐     ┌─────────────────────────────┐
  │   Extract    │────>│       Walk-Forward CV        │
  │   OHLCV     │     │  8mo train / 2mo val / 2mo test
  │  -> parquet  │     │  step every 2 months          │
  └──────────────┘     └──────────────┬──────────────┘
                                      │
                       ┌──────────────v──────────────┐
                       │    CPCV Validation Suite     │
                       │                              │
                       │  Deflated Sharpe Ratio (DSR) │
                       │  Prob. Backtest Overfit (PBO) │
                       │  Combinatorial Purged CV     │
                       └──────────────┬──────────────┘
                                      │
                       ┌──────────────v──────────────┐
                       │    Promotion Gate            │
                       │                              │
                       │  Gate 1: DA >= 0.52          │
                       │  Gate 2: PBO <= 0.30         │
                       │  Gate 3: DSR improvement     │
                       │          >= 0.05             │
                       │                              │
                       │  Pass -> champion alias      │
                       │  Fail -> log, no promotion   │
                       └─────────────────────────────┘
```

### Hourly Serving Pipeline

```
  Per pair/TF:

  OANDA Proxy ──> ingest_ohlcv() ──> compute_features()
                                           |
                      ┌────────────────────┤
                      v                    v
              write_features()     MLflow champion model
              -> fxs_instrument    load + predict()
                 _features              |
                                        v
                                write_predictions()
                                -> fxs_predictions
                                        |
                                        v
                                backfill_actuals()
                                (fill actual_close for
                                 prior predictions)
                                        |
                                        v
                                validate()
                                (sanity checks)

  Then globally:
  aggregate_cross_tf() -> fxs_cross_tf_snapshot
  validate() -> final checks
```

---

## Agent Swarm Deep Dive

### Three-Agent System

```
  ┌─────────────────────────────────────────────────────────────┐
  │                    LangGraph StateGraph                      │
  │                                                              │
  │  ┌────────────────┐                                         │
  │  │   STRATEGIST   │  "What should we try next?"             │
  │  │                │                                         │
  │  │ - Thompson     │  Inputs:                                │
  │  │   Sampling     │    - Bandit allocation                  │
  │  │   allocation   │    - Champion metrics (MLflow)          │
  │  │ - Research     │    - Past experiments (Qdrant)          │
  │  │   context      │    - Research papers (Qdrant)           │
  │  │ - Past         │    - Active insights (ClickHouse)       │
  │  │   experiments  │                                         │
  │  │                │  Output: List[ExperimentSpec]            │
  │  └───────┬────────┘                                         │
  │          v                                                  │
  │  ┌────────────────┐                                         │
  │  │    ENGINEER    │  "How do we implement this?"            │
  │  │                │                                         │
  │  │ - Code gen     │  Input: ExperimentSpec                  │
  │  │   (PyTorch/    │  Process:                               │
  │  │    sklearn/    │    1. Generate Python code              │
  │  │    XGBoost)    │    2. AST sandbox validation            │
  │  │ - AST sandbox  │    3. Retry once if invalid             │
  │  │   validation   │    4. Fallback stub if all fail         │
  │  │                │  Output: experiment_id -> code          │
  │  └───────┬────────┘                                         │
  │          v                                                  │
  │  ┌────────────────┐                                         │
  │  │  META-LEARNER  │  "What did we learn?"                   │
  │  │                │                                         │
  │  │ - ExpeL-style  │  Input: Experiment results              │
  │  │   insight      │  Process:                               │
  │  │   extraction   │    1. Store in ClickHouse + Qdrant      │
  │  │ - Bandit       │    2. Update bandit (reward/penalty)    │
  │  │   state        │    3. Extract insights with confidence  │
  │  │   update       │    4. Categorize: arch, feature, etc.   │
  │  │                │  Output: Updated bandit_state           │
  │  └────────────────┘                                         │
  └─────────────────────────────────────────────────────────────┘
```

### Thompson Sampling Bandit

The bandit balances exploration vs exploitation across 6 research directions:

```
  Arms:
  ┌──────────────┬────────────────────────────────────────────┐
  │ arch_search  │ Try new model architectures (TCN, GRU...) │
  │ feature_eng  │ New feature combinations / transforms      │
  │ strategy     │ New trading strategy logic                  │
  │ ensemble     │ Combine multiple models                    │
  │ regime       │ Regime-conditioned models                  │
  │ refine       │ Hyperparameter tuning on proven setups     │
  └──────────────┴────────────────────────────────────────────┘

  Allocation: 80% exploit (top-performing arms)
              20% explore (underexplored arms)

  Update rule:
    If experiment improved champion:  alpha += 1.0
    If experiment did not improve:    beta  += 1.0
```

### AST Code Sandbox

LLM-generated code is validated before execution:

```
  Allowed imports:
    torch, numpy, pandas, sklearn, xgboost, optuna, mlflow, src.training.*

  Blocked calls:
    os.system, subprocess, eval, exec, __import__, open (except /workspace/)

  Required:
    Must define run_experiment() function
    Must load data from /workspace/data.parquet
    Must log metrics + model to MLflow
    Must write run_id to /tmp/run_id
```

---

## Research Crawler

The crawler runs at the start of each swarm cycle to discover new research:

```
  Sources (configurable in fxs_research_sources):

  arXiv Categories:           Tavily Sites:
  ┌──────────────────┐        ┌─────────────────────┐
  │ q-fin.TR         │        │ quantpedia.com       │
  │ q-fin.CP         │        │ papers.ssrn.com      │
  │ q-fin.PM         │        │ paperswithcode.com   │
  │ q-fin.RM         │        │ arxiv.org            │
  │ cs.LG            │        │ openreview.net       │
  │ cs.AI            │        │ jmlr.org             │
  │ stat.ML          │        │ nber.org             │
  └──────────────────┘        └─────────────────────┘

  Pipeline:
  Fetch -> Dedup (xxhash64) -> Classify (qwen3-32b, score 0.0-1.0)
    -> if score >= 0.4: Chunk (~2000 chars, 10% overlap)
    -> Embed (qwen3-embed-8b, 4096-dim)
    -> Store: Qdrant (fx_research) + ClickHouse (fxs_research_corpus)

  Max 20 new resources per cycle.
```

---

## Training Pipeline

### Feature Engineering

The system computes a standard feature set from OHLCV data:

```
  Returns:          returns_1, returns_5, returns_10, returns_21
  Moving Averages:  sma_5, sma_10, sma_21, sma_50
  Exponential MAs:  ema_5, ema_10, ema_21, ema_50
  Volatility:       volatility_10, volatility_21
  Indicators:       rsi_14, macd, macd_signal, macd_histogram
  Bollinger:        bb_upper, bb_lower, bb_width
  Other:            atr_14, volume_sma_10, volume_ratio, price_vs_sma50
```

### Walk-Forward Cross-Validation

```
  |<---- 8 months ---->|<-- 2mo -->|<-- 2mo -->|
  |     TRAIN          |    VAL    |   TEST    |
  |                    |           |           |
  Step forward 2 months each fold:

  Fold 1: [Jan-Aug]       [Sep-Oct]    [Nov-Dec]
  Fold 2: [Mar-Oct]       [Nov-Dec]    [Jan-Feb]
  Fold 3: [May-Dec]       [Jan-Feb]    [Mar-Apr]
  ...
```

### Supported Model Families

LLM-generated code can use any of these:

| Family | Library | Example Architectures |
|--------|---------|----------------------|
| **Deep Learning** | PyTorch | LSTM, GRU, TCN, Transformer, MLP |
| **Gradient Boosting** | XGBoost | XGBClassifier, XGBRegressor |
| **Classical ML** | scikit-learn | RandomForest, SVM, Ridge, KNN |
| **Hyperparameter Optimization** | Optuna | Tree-structured Parzen Estimators |

---

## Serving Pipeline

### Universe Coverage

```
  G10 Majors:
  ┌──────────┬──────────┬──────────┬──────────┐
  │ USD_JPY  │ EUR_USD  │ GBP_USD  │ AUD_USD  │
  │ USD_CHF  │ USD_CAD  │ NZD_USD  │          │
  └──────────┴──────────┴──────────┴──────────┘

  Timeframes: H1, H4

  Total: 7 pairs x 2 timeframes = 14 models served hourly
```

### Prediction Output

Each hourly prediction writes to `fxs_predictions`:

| Field | Type | Description |
|-------|------|-------------|
| `pair` | String | e.g., USD_JPY |
| `timeframe` | String | H1 or H4 |
| `timestamp` | DateTime | Prediction timestamp |
| `model_registry` | String | MLflow model name |
| `model_version` | UInt32 | MLflow version |
| `architecture` | String | e.g., LSTM, TCN, XGBoost |
| `pred_next_close` | Float64 | Predicted next close price |
| `actual_close` | Nullable(Float64) | Backfilled when available |
| `error_pips` | Nullable(Float64) | Computed after backfill |

---

## Advanced Validation

### Deflated Sharpe Ratio (DSR)

Adjusts the observed Sharpe ratio for:
- **Multiple testing** (number of trials run)
- **Non-normal returns** (skewness, kurtosis)
- **Short track records** (sample size penalty)

Returns the probability that the observed Sharpe is genuine, not luck.

### Probability of Backtest Overfitting (PBO)

Based on Bailey et al. (2017):
- Uses Combinatorially Symmetric Cross-Validation
- Measures how often the best in-sample strategy underperforms out-of-sample
- PBO > 0.50 indicates likely overfitting

### Promotion Gates

All three gates must pass for a model to become champion:

```
  Gate 1: Directional Accuracy >= 0.52
  Gate 2: PBO <= 0.30
  Gate 3: DSR improvement >= 0.05 over current champion
  Bonus:  MIN_OOS_PREDICTIONS >= 500
```

---

## Use Cases

### 1. Autonomous Strategy Discovery

The primary use case: the swarm continuously searches for better FX prediction models without human intervention.

```
  Week 1: Swarm proposes LSTM on USD_JPY H1 with momentum features
          -> Trains on GPU, achieves DSR 1.2, promoted to champion

  Week 2: Swarm proposes TCN variant (informed by arXiv paper)
          -> Outperforms LSTM champion by DSR 0.08, new champion

  Week 3: Meta-Learner notes "TCN > LSTM on JPY pairs consistently"
          -> Insight stored as hard constraint
          -> Future cycles skip LSTM proposals for JPY pairs
```

### 2. Research-Driven Feature Engineering

The crawler finds relevant papers that inform the Strategist:

```
  Crawler discovers: "Volatility clustering in JPY pairs responds to
                      realized variance features" (arXiv q-fin.TR)

  Strategist proposes: Experiment with realized variance features
                       on USD_JPY H1 (citing paper ID)

  Engineer generates: Code computing RV from 5-min returns,
                     feeding into GRU model

  Result: +3% directional accuracy improvement
  Meta-Learner: "Realized variance features improve JPY H1 models"
```

### 3. Overfitting Prevention

The validation suite prevents promoting overfit models:

```
  Candidate model: Sharpe 3.5 in-sample (suspiciously high)

  CPCV validation:
    - Deflated Sharpe: 0.8 (adjusted for 50 prior trials)
    - PBO: 0.65 (best IS strategy underperforms OOS 65% of the time)

  Promotion gate: REJECTED (PBO 0.65 > max 0.30)
  Meta-Learner: "Complex architectures with >20 features overfit on H4"
```

### 4. Multi-Timeframe Consensus

The serving pipeline aggregates predictions across timeframes:

```
  USD_JPY H1 prediction: bullish (pred_next_close > current)
  USD_JPY H4 prediction: bullish (aligned)

  Cross-TF snapshot: trend_aligned = true
  -> Higher confidence signal for downstream consumers
```

### 5. Continuous Model Monitoring

Backfilled actuals enable ongoing model health monitoring:

```
  Prediction at T: pred_next_close = 150.25
  Actual at T+1:   actual_close = 150.18
  Error: 7 pips

  Over time, fxs_predictions builds a complete track record:
  - Rolling accuracy by pair/TF
  - Error distribution analysis
  - Regime-conditioned performance
```

---

## Database Schema

All tables in `cervid_analytics` database with `fxs_` prefix:

```
  ┌─────────────────────────────────────────────────────────────┐
  │                     cervid_analytics                         │
  │                                                              │
  │  Core:                                                       │
  │  ┌─────────────────────┐  ┌──────────────────────┐          │
  │  │ fxs_serving_universe│  │ fxs_instrument       │          │
  │  │ (pairs x TFs)       │  │ _features (OHLCV+)   │          │
  │  └─────────────────────┘  └──────────────────────┘          │
  │                                                              │
  │  Predictions:                                                │
  │  ┌─────────────────────┐  ┌──────────────────────┐          │
  │  │ fxs_predictions     │  │ fxs_cross_tf_snapshot│          │
  │  │ (hourly forecasts)  │  │ (multi-TF consensus) │          │
  │  └─────────────────────┘  └──────────────────────┘          │
  │                                                              │
  │  Swarm:                                                      │
  │  ┌─────────────────────┐  ┌──────────────────────┐          │
  │  │ fxs_experiments     │  │ fxs_insights         │          │
  │  │ (full experiment    │  │ (ExpeL-style rules)  │          │
  │  │  history + metrics) │  │                      │          │
  │  └─────────────────────┘  └──────────────────────┘          │
  │                                                              │
  │  Research:                                                   │
  │  ┌─────────────────────┐  ┌──────────────────────┐          │
  │  │ fxs_research_sources│  │ fxs_research_corpus  │          │
  │  │ (arxiv + tavily)    │  │ (embedded chunks)    │          │
  │  └─────────────────────┘  └──────────────────────┘          │
  │  ┌─────────────────────┐                                    │
  │  │ fxs_research        │                                    │
  │  │ _crawl_log (dedup)  │                                    │
  │  └─────────────────────┘                                    │
  └─────────────────────────────────────────────────────────────┘
```

### Key Tables

| Table | Engine | Partition | Order | Purpose |
|-------|--------|-----------|-------|---------|
| `fxs_serving_universe` | MergeTree | - | (pair, timeframe) | Active pair/TF combos |
| `fxs_instrument_features` | MergeTree | toYYYYMM(timestamp) | (pair, timeframe, timestamp) | OHLCV + computed features |
| `fxs_predictions` | MergeTree | toYYYYMM(timestamp) | (pair, timeframe, timestamp) | Predictions with backfilled actuals |
| `fxs_experiments` | MergeTree | toYYYYMM(created_at) | (swarm_cycle, experiment_id) | Full experiment log |
| `fxs_insights` | MergeTree | - | (category, insight_id) | ExpeL constraints |
| `fxs_research_corpus` | MergeTree | - | (entry_id, chunk_index) | Embedded research chunks |
| `fxs_cross_tf_snapshot` | MergeTree | toYYYYMM(snapshot_ts) | (pair, snapshot_ts) | Multi-TF aggregation |

### Seeded Data

- **fxs_serving_universe**: G10 majors (USD_JPY, EUR_USD, GBP_USD, AUD_USD, USD_CHF, USD_CAD, NZD_USD) x {H1, H4}
- **fxs_research_sources**: 7 arXiv categories + 7 Tavily sites

---

## Infrastructure

### Docker Images

| Image | Base | Purpose | Entrypoint |
|-------|------|---------|-----------|
| `fx-training` | pytorch:2.2.0-cuda12.1 | GPU training, Optuna HPO, walk-forward CV, CPCV | `src.training.executor` |
| `fx-orchestrator` | python:3.11-slim | LangGraph swarm graph, Hera workflow submission | `src.swarm.graph` |
| `fx-serving` | python:3.11-slim | Hourly OHLCV ingestion, feature computation, inference | `src.serving.process_pair_tf` |
| `fx-ops` | python:3.11-slim | Data extraction, universe loading, database setup | Various |

### Argo CronWorkflows

| Workflow | Schedule | Duration | Description |
|----------|----------|----------|-------------|
| `fx-swarm` | Weekly (Sun 00:00) | Up to 24h | LangGraph swarm loop: crawl -> strategize -> design -> execute -> evaluate -> learn |
| `fx-training-monthly` | Monthly (1st, 02:00) | Up to 12h | Retrain all pair x TF combos with walk-forward + CPCV |
| `fx-serving` | Hourly (:05) | ~10 min | Ingest, predict, backfill, aggregate, validate |

### Kubernetes Resources

```
  Node Pools:
  ┌─────────────┐  ┌──────────────┐
  │  GPU Pool   │  │  CPU Pool    │
  │             │  │              │
  │ - Training  │  │ - Orchestrator│
  │   pods      │  │ - Ops pods   │
  │ (1x GPU,    │  │ - Serving    │
  │  16Gi mem)  │  │ - Extract    │
  └─────────────┘  └──────────────┘

  Security:
  - gVisor RuntimeClass for sandboxed code execution
  - NetworkPolicies for pod-to-pod isolation
  - Doppler-synced K8s secrets (argo-data-science-swarm)
```

### External Services

| Service | Purpose | Auth |
|---------|---------|------|
| **Novita AI** | LLM (Qwen 3.5 397B analysis, Qwen 3 32B routing, Qwen 3 Embed 8B) | NOVITA_API_KEY |
| **Qdrant** | Vector memory (experiments + research) | QDRANT_HOST/PORT |
| **ClickHouse** | Time-series analytics backbone | CLICKHOUSE_* |
| **MLflow** | Model registry + experiment tracking | MLFLOW_TRACKING_URI |
| **OANDA Proxy** | FX data via caching layer | OANDA_PROXY_URL |
| **arXiv** | Research papers (public API) | None |
| **Tavily** | Web search + extraction | TAVILY_API_KEY |
| **DragonflyDB** | LangGraph state persistence (Redis-compatible) | DRAGONFLY_URL |
| **Discord** | Notifications (promotions, circuit breaks) | DISCORD_WEBHOOK_URL |
| **DO Spaces** | S3 artifact store for MLflow + Argo | AWS_ACCESS_KEY_ID/SECRET |

---

## Components

### Directory Structure

```
data_scientist_agent_swarm_research/
├── .env.example                        # All environment variables with descriptions
├── pyproject.toml                      # Project metadata (fx-research-swarm)
├── requirements-training.txt           # Training image deps (PyTorch, Optuna, etc.)
├── requirements-ops.txt                # Ops image deps (ClickHouse, OANDA client)
├── requirements-serving.txt            # Serving image deps (MLflow, feature compute)
├── requirements-orchestrator.txt       # Orchestrator deps (LangGraph, Hera, Qdrant)
├── argo/
│   ├── swarm-cronworkflow.yaml         # Weekly LangGraph swarm orchestrator
│   ├── training-cronworkflow.yaml      # Monthly retrain all pairs
│   ├── serving-cronworkflow.yaml       # Hourly inference pipeline
│   └── artifact-repo-config.yaml       # S3 artifact repository config
├── docker/
│   ├── training.Dockerfile
│   ├── ops.Dockerfile
│   ├── serving.Dockerfile
│   └── orchestrator.Dockerfile
├── doppler/
│   ├── push.sh                         # Push secrets: ./push.sh <dev|prd>
│   └── env.example                     # Template for env.dev / env.prd
├── k8s/
│   ├── clickhouse-tables.sql           # Full ClickHouse schema (fxs_* tables)
│   ├── network-policies.yaml           # K8s NetworkPolicy definitions
│   └── gvisor-runtime-class.yaml       # gVisor sandbox RuntimeClass
├── scripts/
│   └── database_setup.py              # ClickHouse schema initializer
└── src/
    ├── shared/
    │   ├── config.py                   # SharedConfig (pydantic-settings singleton)
    │   ├── ch_client.py                # ClickHouse client factory
    │   ├── mlflow_utils.py             # MLflow helpers
    │   ├── llm_client.py               # Novita AI / OpenAI-compatible client
    │   ├── oanda.py                    # OANDA proxy client with retry
    │   └── discord.py                  # Discord webhook notifications
    ├── swarm/
    │   ├── graph.py                    # LangGraph StateGraph definition
    │   ├── state.py                    # SwarmState schema
    │   ├── bandit.py                   # Thompson Sampling multi-armed bandit
    │   ├── evaluator.py                # Deterministic experiment evaluation
    │   ├── sandbox.py                  # AST code validation
    │   ├── hera_submit.py              # Hera-based Argo Workflow submission
    │   ├── agents/
    │   │   ├── strategist.py           # Hypothesis generation agent
    │   │   ├── engineer.py             # Code generation agent
    │   │   └── meta_learner.py         # Insight extraction agent
    │   ├── memory/
    │   │   ├── qdrant_store.py         # Experiment vector operations
    │   │   ├── insight_store.py        # ExpeL-style insight CRUD
    │   │   ├── research_store.py       # Research corpus retrieval
    │   │   └── clickhouse_analytics.py # Experiment history queries
    │   ├── research/
    │   │   └── crawler.py              # arXiv + Tavily research crawler
    │   └── prompts/
    │       ├── strategist_system.md
    │       ├── strategist_user.md
    │       ├── engineer_system.md
    │       ├── engineer_user.md
    │       ├── meta_learner_system.md
    │       └── meta_learner_user.md
    ├── training/
    │   ├── executor.py                 # Generic experiment runner (loads code from S3)
    │   ├── extract_training_data.py    # OHLCV extraction
    │   ├── features.py                 # Feature engineering
    │   ├── sequences.py                # Time-series windowing
    │   ├── walk_forward.py             # Walk-forward validation splits
    │   ├── validate_data.py            # Data quality checks
    │   ├── promotion_gate.py           # Model promotion criteria
    │   ├── pyfunc_wrapper.py           # MLflow pyfunc model wrapper
    │   └── scaffolding/
    │       ├── data_loader.py          # PyTorch DataLoader factory
    │       ├── training_loop.py        # Generic training loop + early stopping
    │       ├── metrics.py              # Sharpe, accuracy, drawdown metrics
    │       └── mlflow_log.py           # MLflow logging utilities
    ├── serving/
    │   ├── process_pair_tf.py          # Per-pair/TF processing entry point
    │   ├── ingest_ohlcv.py             # OHLCV ingestion
    │   ├── compute_features.py         # Real-time feature computation
    │   ├── serve_model.py              # MLflow model loading + inference
    │   ├── write_clickhouse.py         # Prediction writes
    │   ├── backfill_actuals.py         # Backfill actual close prices
    │   ├── aggregate_cross_tf.py       # Cross-timeframe snapshot aggregation
    │   └── validate.py                 # Prediction validation
    └── cpcv/
        ├── purged_cv.py                # Combinatorial Purged Cross-Validation
        ├── deflated_sharpe.py          # Deflated Sharpe Ratio
        └── pbo.py                      # Probability of Backtest Overfitting
```

---

## Setup

### 1. Doppler Secrets

```bash
cd doppler
cp env.example env.dev
# Fill in all values in env.dev
./push.sh dev

# For production:
cp env.example env.prd
./push.sh prd
```

Doppler project: `data-science-swarm`

### 2. ClickHouse Schema

Apply the full schema (creates `fxs_*` tables in `cervid_analytics` with seed data):

```bash
python scripts/database_setup.py
# or apply manually:
# clickhouse-client --host $CLICKHOUSE_HOST < k8s/clickhouse-tables.sql
```

Tables created: `serving_universe`, `instrument_features`, `predictions`, `cross_tf_snapshot`, `experiments`, `insights`, `research_sources`, `research_crawl_log`, `research_corpus`

### 3. Qdrant Collections

The orchestrator auto-creates collections on first run:
- `fx_experiments` -- experiment embedding vectors for similarity search
- `fx_research` -- research corpus chunk embeddings

### 4. Apply Argo CronWorkflows

```bash
kubectl apply -f argo/swarm-cronworkflow.yaml -n argo-workflows
kubectl apply -f argo/training-cronworkflow.yaml -n argo-workflows
kubectl apply -f argo/serving-cronworkflow.yaml -n argo-workflows
```

---

## Running

### Submit Individual Workflows

```bash
# Weekly swarm orchestrator (on-demand)
argo submit --from cronworkflow/fx-swarm -n argo-workflows

# Monthly retrain (on-demand)
argo submit --from cronworkflow/fx-training-monthly -n argo-workflows

# Hourly serving pipeline (on-demand)
argo submit --from cronworkflow/fx-serving -n argo-workflows
```

### Monitor

```bash
# Watch running workflows
argo list -n argo-workflows --running

# Stream logs from a specific workflow
argo logs <workflow-name> -n argo-workflows --follow

# Check CronWorkflow schedules
argo cron list -n argo-workflows
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key groups:

| Group | Variables | Notes |
|-------|-----------|-------|
| Data Source | `OANDA_PROXY_URL` | Points to `oanda-caching-api` |
| ClickHouse | `CLICKHOUSE_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_DB` | Database: `cervid_analytics` |
| MLflow | `MLFLOW_TRACKING_URI`, `MLFLOW_S3_ENDPOINT_URL`, `AWS_*` | DO Spaces for artifacts |
| LLM | `NOVITA_API_KEY`, `LLM_ANALYSIS_MODEL`, `LLM_ROUTING_MODEL` | Novita AI (Qwen models) |
| Training | `EPOCHS`, `OPTUNA_TRIALS`, `SEQUENCE_LENGTH`, `BATCH_SIZE` | HPO and training config |
| Swarm | `QDRANT_HOST`, `QDRANT_PORT`, `EXPLORATION_BUDGET_PCT` | Vector memory + bandit |
| Promotion | `MIN_DIRECTIONAL_ACCURACY`, `MAX_PBO`, `DSR_IMPROVEMENT_THRESHOLD` | Model promotion gates |
| Infra | `GPU_NODE_POOL`, `CPU_NODE_POOL`, `ARGO_NAMESPACE` | K8s scheduling |

---

## CI/CD

GitHub Actions workflow: `.github/workflows/fx-swarm-ci.yaml`

Builds 4 Docker images in parallel on push to `main` (path: `data_scientist_agent_swarm_research/**`):

```
fx-training, fx-ops, fx-serving, fx-orchestrator
```

Images are pushed to `registry.digitalocean.com/ams3-digitalocean-cervid-registry` with tags `prod-<commit-hash>` and `latest`.

---

## License

Apache 2.0 -- See repository root [LICENSE](../LICENSE).
