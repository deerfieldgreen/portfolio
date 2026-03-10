# Market Regime API vs Argo Pipeline — Review

## 1. Workflow and assumptions

### 1.1 Argo pipeline (market_regime_detection)

**Sequence:**  
`setup-tables` → `process-usdjpy-h1` → `process-usdjpy-h4` → `train-usdjpy-h1` → `train-usdjpy-h4`

**Assumptions:**

- **Data:** OANDA is the source of truth. Process step fetches OHLCV (config: `lookback_days`, default 365), computes features (log return, rolling volatility, RSI, MACD, ATR), optionally adds macro differentials (config: `macro_indicators.enabled`).
- **Storage:** Single ReadWriteOnce PVC (`workspace`). Process steps write `{pair}_{timeframe}.csv`; train steps read the same paths. No cross-step artifacts beyond that.
- **Model:** One HMM per (pair, timeframe). Features: `log_return`, `volatility`, `rsi`, `macd`, `atr` (+ any `*_diff` macro columns). Fixed 3-state Gaussian HMM (config: `n_states: 3`, full covariance). GARCH is fitted but **not** written to ClickHouse; only HMM outputs and transition matrix are persisted.
- **ClickHouse:** Setup creates tables in `CLICKHOUSE_DATABASE` via SQL under `data_processing/sql/`. Train step inserts regime rows and one transition-matrix row per run; it uses table names from `config.yaml` (see table-name mismatch below).
- **Scope:** Only USD_JPY, H1 and H4. Workflow arguments `pairs` / `timeframes` are not used by the DAG; the four steps are hardcoded.

### 1.2 Market Regime API

**Assumptions:**

- **Data source:** Read-only. All data comes from ClickHouse tables `regime_states` and `transition_matrices` in the database given by `CLICKHOUSE_DATABASE` (Doppler). No OANDA or pipeline code runs inside the API.
- **Semantics:** “Current” = latest row per (pair, timeframe). History = filtered, ordered by timestamp DESC, limited. Forecast = Markov chain propagation from current state using latest transition matrix. Validate = latest row’s model metrics (AIC, BIC, log_likelihood, n_states, confidence).
- **Caching:** All read endpoints use a single TTL cache (Doppler: `CERVID_CACHE_TTL_SECONDS`, min 36_000). Cache key is (prefix, args, kwargs); no database or table name in the key, so same API instance = same logical view of the DB for the TTL window.

---

## 2. Outputs: pipeline vs API

| Concept | Pipeline (Argo) | API |
|--------|------------------|-----|
| **Regime state** | Per-row `regime_state` (0/1/2) from HMM Viterbi | Same: `regime_state` from latest row |
| **State probabilities** | `state_prob_0/1/2` per row from `predict_proba` | Exposed as `state_probabilities` list |
| **Confidence** | `max(state_probs)` per row | `confidence_score` from same column |
| **Emission params** | `mean_returns_per_state`, `volatility_per_state` (arrays) from empirical state returns | Same columns in current and history |
| **Regime metadata** | `regime_change`, `regime_duration` from post-processing | Exposed in current and history |
| **Model metrics** | AIC, BIC, log_likelihood, n_states on every row | Validate endpoint returns them from latest row |
| **Transition matrix** | One row per train run in transitions table | Forecast uses latest row; propagates distribution |
| **Features** | log_return, volatility, rsi, macd, atr (and macro) in DF; all written to DB | API returns log_return, volatility; not rsi/macd/atr in response schemas |

So: the API exposes a **subset** of what the pipeline writes. Column-wise, the API’s SELECTs match the pipeline’s insert columns for the fields that are exposed. The only structural mismatch is **table names** (see below).

---

## 3. Critical issue: table names (pipeline DDL vs config vs API)

- **DDL (setup_tables + SQL):** Creates `mr_regime_states` and `mr_transition_matrices`.
- **Config (`config.yaml`):** `clickhouse.tables.regimes: "regime_states"`, `transitions: "transition_matrices"`.
- **Pipeline (train_model.py):** Inserts into the config table names → **`regime_states`** and **`transition_matrices`**.
- **API (routers/regimes.py):** Queries **`regime_states`** and **`transition_matrices`** (hardcoded).

So:

- The **API** and the **pipeline’s config** agree on names: `regime_states`, `transition_matrices`.
- The **setup_tables** step never creates those names; it only creates `mr_regime_states` and `mr_transition_matrices`.

If the database is created only by this workflow, the first train step will try to insert into `regime_states`, which does not exist, and the insert will fail. For the API to work, either:

1. There are views (or synonyms) mapping `regime_states` → `mr_regime_states` and `transition_matrices` → `mr_transition_matrices`, or  
2. Tables were created elsewhere with the non-`mr_` names, or  
3. One side is wrong: either config + API should use `mr_*`, or DDL should create `regime_states` / `transition_matrices`.

**Recommendation:** Align DDL, config, and API on one naming scheme (e.g. use `mr_*` in config and API, or change DDL to create `regime_states` / `transition_matrices` and drop the `mr_` prefix). Document the chosen convention.

---

## 4. Business logic and consistency

### 4.1 Forecast horizon vs actual steps

- **API:** `horizon` is in days (e.g. 30). Response has `horizon_days: horizon` and `forecast_date: now + horizon days`.
- **Logic:** `n_steps = min(horizon * steps_per_day, 100)`. For H1, steps_per_day = 24, so for 30 days that’s 720 steps, capped at **100**. So the forecast distribution is for **100 bars** (≈4.17 days for H1), not 30 days.
- **Effect:** Clients are told “forecast for 30 days” but the probability vector is for ~4 days. Either cap and document (e.g. “max 100 steps”) or remove the cap and allow true 30-day propagation (and consider performance).

### 4.2 “Current” regime

- Pipeline writes one row per (timestamp, pair, timeframe) for the **historical** window it trained on. “Current” in the API is “latest timestamp in DB,” i.e. the most recent bar the pipeline wrote, which is the end of the lookback window at train time.
- So “current” is **not** live: it only moves when the pipeline runs again and appends new rows. That’s consistent with a batch design but should be clear to API users (e.g. “current = latest trained bar”).

### 4.3 Validation metrics

- Validate endpoint returns AIC, BIC, log_likelihood, n_states, confidence from the **latest** regime_states row. Those metrics are identical for every row in a given train run (they’re copied from the same model). So “validation” is really “model quality of the last run,” not a separate validation set. Naming is slightly misleading but logically fine if documented.

### 4.4 GARCH

- Pipeline fits GARCH for volatility but does **not** persist GARCH parameters or forecasts. Only HMM states, probabilities, and transition matrix are stored. So the API cannot expose GARCH; if the intent was to use GARCH for volatility in the API, that’s missing.

### 4.5 Macro features

- `config.yaml` has `macro_indicators.enabled: true` but `process_data.add_macro_features` uses **mock random data** (with a clear warning in code). That violates the “no synthetic data” rule for production and can distort regime detection. Either disable macro or wire real sources (e.g. FRED) and document.

### 4.6 Mock data path

- `process_data.py` has `_generate_mock_data` for when OANDA is unavailable. It’s not used in the main path (main calls `fetch_oanda_data` only). If it’s only for local/testing, it should be clearly gated (e.g. env flag) so it never runs in production.

---

## 5. Workflow and infra details

- **GPU:** The workflow has `nodeSelector: pool-1riu8gbjx-gpu` and tolerations for `nvidia.com/gpu`. Market regime detection is CPU-only (HMM + GARCH). Per project rules, this pipeline should **not** request GPU; the selector/tolerations can cause unnecessary scheduling on GPU nodes.
- **Config for train step:** Train container gets `config.yaml` from the image (regime_modeling Dockerfile). The **train-step** in `market_regime_detection.yaml` does **not** define `CLICKHOUSE_DATABASE` in its env (only setup-tables does). `train_model.get_clickhouse_client()` uses `os.environ["CLICKHOUSE_DATABASE"]`, so as written the train step would raise **KeyError** on first ClickHouse use. Add `CLICKHOUSE_DATABASE` from the same secret to the train-step env.
- **Process step:** Does **not** receive ClickHouse env vars (correct — it only writes CSV to the shared volume).

---

## 6. Summary of recommendations

1. **Table names:** Unify DDL, config, and API on either `mr_regime_states`/`mr_transition_matrices` or `regime_states`/`transition_matrices` (and add views if you keep both for legacy).
2. **Forecast:** Either document that forecast is capped at 100 steps (and adjust `forecast_date`/description) or remove the cap and support true horizon_days.
3. **GPU:** Remove GPU nodeSelector and tolerations from this WorkflowTemplate so it’s CPU-only.
4. **CLICKHOUSE_DATABASE:** The train step currently does **not** have `CLICKHOUSE_DATABASE` in its env; add it (from `market-regime-detection-secrets`) so the client uses the same database as setup-tables and the API.
5. **Macro:** Disable macro or replace mock data with real data; document and align with “no synthetic data” for production.
6. **GARCH:** If GARCH is for production use, persist it (e.g. table or columns) and expose via API; otherwise document that it’s diagnostic-only.

---

## 7. Questions for you

1. **Table names:** In the environment where this runs, do `regime_states` and `transition_matrices` exist as views over `mr_*`, or are they separate tables? That determines whether we fix config/DDL or add views.
2. **Forecast cap:** Is the 100-step cap intentional (e.g. to avoid slow requests)? If yes, should the API response explicitly say “forecast for 100 bars” or “effective horizon ≈ 4 days for H1” instead of “horizon_days: 30”?
3. **“Current” regime:** Do you want the API to document that “current” = “latest bar written by the last pipeline run” (no live tick)?
4. **Train step CLICKHOUSE_DATABASE:** The workflow YAML does not pass `CLICKHOUSE_DATABASE` into the train-step; the code expects it and would KeyError. Is it injected elsewhere (e.g. Argo workflow controller env), or is this a bug that’s never been run end-to-end?
5. **Macro in production:** Should macro be disabled until FRED (or similar) is integrated, or is mock data acceptable for a non-production environment only?
