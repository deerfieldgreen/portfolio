# Market Regime Detection System

A comprehensive system for detecting market regimes in forex pairs using Hidden Markov Models (HMM) and GARCH volatility modeling. This system provides automated regime detection, historical tracking, and real-time API access for AI agents and trading systems.

## 🎯 Overview

This system implements market regime detection for forex pairs (USD/JPY, EUR/USD) across multiple timeframes (H1, H4, Daily). It uses:

- **Hidden Markov Models (HMM)** for regime classification
- **GARCH models** for volatility modeling
- **Technical indicators** (RSI, MACD, ATR) for feature engineering
- **Macroeconomic differentials** for enhanced regime context
- **ClickHouse** for efficient time-series data storage
- **FastAPI** for RESTful API access

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Argo Workflow Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   Initialize │    │ Data Process │    │   Enrich     │    │ Train Model  │ │
│  │  ClickHouse  │───▶│   (Fetch &   │───▶│ (z-score,    │───▶│   (HMM &     │ │
│  │    Tables    │    │   Features)  │    │  PCA, SMA/   │    │    GARCH)    │ │
│  └──────────────┘    └──────────────┘    │  EMA, skew)  │    └──────┬───────┘ │
│                                           └──────────────┘           │          │
│                                                   │          │
│                                                   ▼          │
│                                         ┌──────────────────┐│
│                                         │   ClickHouse     ││
│                                         │  (regime_states, ││
│                                         │   transitions)   ││
│                                         └────────┬─────────┘│
└──────────────────────────────────────────────────┼──────────┘
                                                    │
                                                    ▼
                                         ┌──────────────────┐
                                         │   FastAPI Server │
                                         │   (Query & API)  │
                                         └──────────────────┘
```

## 📊 Data Points Logged

### Core Model Outputs
- **Regime State**: Integer classification (0=low-vol/bull, 1=high-vol/bear, 2=neutral)
- **State Probabilities**: Array of probabilities for each state (sums to 1.0)
- **Confidence Score**: Maximum state probability
- **Transition Matrix**: State-to-state transition probabilities

### Emission Parameters
- **Mean Returns per State**: Average log returns for each regime
- **Volatility per State**: Standard deviation of returns for each regime

### Enrichment (before training, fit on each run)
- **Z-score**: Base features (log return, volatility, RSI, MACD, ATR) and macro series standardized to mean 0, std 1.
- **PCA**: Applied to z-scored macro only; components explain 95% variance (max 5). Raw macro replaced by PC1..PC5 for HMM input.
- **SMA/EMA**: Windows 30, 50, 100, 200 computed on each PC series (trend context).
- **Skew/kurtosis**: Per PC over the full window (distribution shape). All enriched columns are persisted to `mr_regime_states`.

### Input Features (to HMM)
- **Base (z-scored)**: log_return_z, volatility_z, rsi_z, macd_z, atr_z
- **Macro (when not enriched)**: raw *_diff columns. When enriched: **PC1..PC5** plus **SMA/EMA(30,50,100,200)** and **skew/kurtosis** per PC.

### Macroeconomic Differentials (US minus foreign)
- Interest rate differentials (2-year, 10-year, policy rates)
- CPI year-over-year differential
- GDP growth differential
- Unemployment rate differential
- PMI composite differential

### Model Metadata
- **Model Quality**: AIC, BIC, log-likelihood
- **Model Parameters**: n_states, covariance_type
- **Regime Metadata**: Duration in current regime, change flags

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Docker
- ClickHouse database
- OANDA API key (or alternative data source)
- Kubernetes cluster with Argo Workflows (for production)

### Installation

1. **Install Python dependencies:**

```bash
# For data processing
cd data_processing
pip install -r requirements.txt

# For regime modeling
cd ../regime_modeling
pip install -r requirements.txt

# For API
cd ../api
pip install -r requirements.txt
```

2. **Configure environment variables:**

```bash
# ClickHouse
export CLICKHOUSE_HOST=your-clickhouse-host
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_USERNAME=default
export CLICKHOUSE_PASSWORD=your-password
export CLICKHOUSE_SECURE=true

# Data source
export OANDA_API_KEY=your-oanda-key
```

3. **Initialize ClickHouse tables:**

```bash
cd scripts
python init_clickhouse.py
```

### Local Development

1. **Process data:**

```bash
cd data_processing
export PAIR=USD_JPY
export TIMEFRAME=H1
export OUTPUT_PATH=/tmp/processed_data.csv
python process_data.py
```

2. **Train model and log to ClickHouse:**

```bash
cd ../regime_modeling
export INPUT_PATH=/tmp/processed_data.csv
export OUTPUT_PATH=/tmp/regime_results.csv
python train_model.py
```

3. **Run API server:**

```bash
cd ../api
uvicorn api:app --host 0.0.0.0 --port 8000
```

4. **Access API documentation:**

Open browser to `http://localhost:8000/docs`

## 📡 API Endpoints

### Core Endpoints

#### 1. List Available Pairs
```http
GET /regimes/pairs
```

Returns list of available currency pairs with timeframes and last update timestamps.

#### 2. Get Current Regime
```http
GET /regimes/current/{pair}?timeframe=H1
```

Returns the current regime state for a specific pair and timeframe.

**Example response:**
```json
{
  "pair": "USD_JPY",
  "timeframe": "H1",
  "timestamp": "2026-02-10T12:00:00",
  "regime_state": 0,
  "state_probabilities": [0.85, 0.12, 0.03],
  "confidence_score": 0.85,
  "mean_returns_per_state": [0.0005, -0.001, 0.0003],
  "volatility_per_state": [0.008, 0.025, 0.015],
  "log_return": 0.0004,
  "volatility": 0.009,
  "regime_duration": 45
}
```

#### 3. Get Regime History
```http
GET /regimes/history/{pair}?timeframe=H1&start_date=2025-01-01&limit=100
```

Returns historical regime data with optional date filters.

#### 4. Forecast Future Regimes
```http
GET /regimes/forecast/{pair}?timeframe=H1&horizon=30
```

Forecasts future regime probabilities using transition matrices.

**Example response:**
```json
{
  "pair": "USD_JPY",
  "timeframe": "H1",
  "forecast_date": "2026-03-12T00:00:00",
  "current_state": 0,
  "forecasted_states": [
    {"state": 0, "probability": 0.72},
    {"state": 1, "probability": 0.20},
    {"state": 2, "probability": 0.08}
  ],
  "horizon_days": 30
}
```

#### 5. Get Model Validation Metrics
```http
GET /regimes/validate/{pair}?timeframe=H1
```

Returns model quality metrics (AIC, BIC, log-likelihood).

### Health Check
```http
GET /health
```

## 🔧 Configuration

Edit `config.yaml` to customize:

- **Pairs and timeframes**: Add or remove currency pairs
- **HMM parameters**: Number of states, covariance type, iterations
- **GARCH parameters**: Lag orders, volatility process, error distribution
- **Feature engineering**: Window sizes for indicators
- **Macro indicators**: Enable/disable and configure sources
- **ClickHouse settings**: Database, tables, partitioning

## 🐳 Docker Deployment

### Build Images

```bash
# Data processing
cd data_processing
docker build -t market-regime-data-processing:latest .

# Regime modeling
cd ../regime_modeling
docker build -t market-regime-modeling:latest .

# API
cd ../api
docker build -t market-regime-api:latest .
```

### Run Containers

```bash
# API server
docker run -d \
  -p 8000:8000 \
  -e CLICKHOUSE_HOST=your-host \
  -e CLICKHOUSE_PORT=8123 \
  -e CLICKHOUSE_USERNAME=default \
  -e CLICKHOUSE_PASSWORD=your-password \
  market-regime-api:latest
```

## ☸️ Kubernetes/Argo Deployment

1. **Build and push images to registry:**

```bash
docker tag market-regime-data-processing:latest registry.digitalocean.com/your-registry/market-regime-data-processing:latest
docker push registry.digitalocean.com/your-registry/market-regime-data-processing:latest

docker tag market-regime-modeling:latest registry.digitalocean.com/your-registry/market-regime-modeling:latest
docker push registry.digitalocean.com/your-registry/market-regime-modeling:latest

docker tag market-regime-api:latest registry.digitalocean.com/your-registry/market-regime-api:latest
docker push registry.digitalocean.com/your-registry/market-regime-api:latest
```

2. **Create Kubernetes secrets:**

```bash
kubectl create secret generic doppler-pipeline \
  --from-literal=CLICKHOUSE_HOST=your-host \
  --from-literal=CLICKHOUSE_PORT=8123 \
  --from-literal=CLICKHOUSE_USERNAME=default \
  --from-literal=CLICKHOUSE_PASSWORD=your-password \
  --from-literal=OANDA_API_KEY=your-key \
  -n argo-workflows
```

3. **Deploy Argo workflow:**

```bash
kubectl apply -f argos/market_regime_detection.yaml
```

4. **Trigger workflow:**

```bash
argo submit argos/market_regime_detection.yaml -n argo-workflows
```

## 🗄️ ClickHouse Schema

### regime_states Table

Primary table for storing regime detection results:

```sql
CREATE TABLE market_regimes.regime_states (
    timestamp DateTime64(3),
    pair String,
    timeframe String,
    regime_state UInt8,
    state_prob_0 Float32,
    state_prob_1 Float32,
    state_prob_2 Float32,
    confidence_score Float32,
    mean_returns_per_state Array(Float32),
    volatility_per_state Array(Float32),
    log_return Float32,
    volatility Float32,
    rsi Float32,
    macd Float32,
    atr Float32,
    -- Macro differentials (optional)
    interest_rate_2y_diff Nullable(Float32),
    interest_rate_10y_diff Nullable(Float32),
    policy_rate_diff Nullable(Float32),
    cpi_yoy_diff Nullable(Float32),
    gdp_growth_diff Nullable(Float32),
    unemployment_diff Nullable(Float32),
    pmi_composite_diff Nullable(Float32),
    -- Model metadata
    n_states UInt8,
    aic Float32,
    bic Float32,
    log_likelihood Float32,
    regime_duration UInt16,
    regime_change UInt8,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, timestamp);
```

### transition_matrices Table

Stores HMM transition matrices:

```sql
CREATE TABLE market_regimes.transition_matrices (
    timestamp DateTime DEFAULT now(),
    pair String,
    timeframe String,
    n_states UInt8,
    transition_matrix Array(Array(Float32)),
    model_version String DEFAULT 'v1',
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (pair, timeframe, timestamp);
```

### Materialized Views

- **mv_current_regimes**: Latest regime for each pair/timeframe
- **mv_regime_statistics**: Aggregated statistics by regime state

## 📈 Use Cases

### For AI Agents

1. **Current Regime Query**: Check current market regime before making trading decisions
2. **Regime History Analysis**: Analyze past regime transitions for pattern recognition
3. **Forecast Integration**: Use regime forecasts in risk management strategies
4. **Validation Checks**: Verify model quality before trusting regime classifications

### For Trading Systems

1. **Regime-Aware Strategies**: Adapt strategy parameters based on detected regime
2. **Risk Management**: Adjust position sizing based on volatility regime
3. **Signal Filtering**: Filter signals based on regime confidence scores
4. **Portfolio Allocation**: Diversify across pairs with different regimes

## 🔬 Model Details

### Hidden Markov Model (HMM)

- **States**: 3 hidden states representing market regimes
  - State 0: Low volatility / Bull market
  - State 1: High volatility / Bear market
  - State 2: Neutral / Sideways market
- **Observations**: Multi-dimensional features (returns, volatility, indicators, macros)
- **Training**: Baum-Welch algorithm (Expectation-Maximization)
- **Inference**: Viterbi algorithm for most likely state sequence

### GARCH Model

- **Purpose**: Volatility forecasting and clustering
- **Default**: GARCH(1,1) with normal distribution
- **Output**: Conditional volatility estimates for each period

### Feature Engineering

- **Returns**: Log returns for stationarity
- **Volatility**: Rolling standard deviation (20-period)
- **Technical Indicators**: RSI, MACD, ATR for momentum and trend
- **Macro Differentials**: Country-pair economic indicator differences

## 🗃️ ClickHouse Admin Setup (One-Time)

The pipeline uses the `market_regime` user. Create it before the first workflow run:

```bash
# 1. Copy env.init.example to env.init, set root password and MARKET_REGIME_USER_PASSWORD
# 2. Push init config: ./push.sh init
# 3. Run admin setup:
cd doppler && doppler run --config prd_init -- ../scripts/init_admin.sh
# 4. Set market_regime password in env.prd, then: ./push.sh prd
```

## ✅ Validating ClickHouse Data

After a workflow run, validate that data was inserted correctly:

```bash
# From local (requires Doppler with prd config)
cd doppler && doppler run --config prd -- python ../scripts/validate_clickhouse.py
```

The script checks:
- **regime_states**: Row counts per pair/timeframe, timestamp ranges, sample row sanity
- **transition_matrices**: 6 rows (one per pair/timeframe), matrix dimensions

### ClickHouse Connection Issues

```bash
# Test connection
export CLICKHOUSE_HOST=your-host
python -c "import clickhouse_connect; client = clickhouse_connect.get_client(host='$CLICKHOUSE_HOST'); print(client.command('SELECT 1'))"
```

### OANDA API Issues

```bash
# Test API key
export OANDA_API_KEY=your-key
python -c "import oandapyV20; print('API key valid')"
```

### Model Training Issues

- Ensure sufficient data (minimum 100 data points recommended)
- Check for NaN values in features
- Verify feature scaling if model doesn't converge

## 📝 License

This project is part of the Cervid quantitative trading platform.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## 📧 Contact

For questions or issues, please open an issue in the repository.

---

Built with ❤️ for the Cervid platform
