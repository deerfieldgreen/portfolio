# src/shared/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List

class SharedConfig(BaseSettings):
    """Single source of truth. Every script imports this.
    Fields used only by specific workflows are Optional with defaults."""

    # ── Data Source ──
    OANDA_PROXY_URL: str = "https://api.cervid.deerfieldgreen.com/v1/oanda"
    OANDA_FETCH_RETRIES: int = 3
    OANDA_FETCH_BACKOFF_BASE: float = 2.0

    # ── ClickHouse ──
    CLICKHOUSE_HOST: str = "clickhouse"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USERNAME: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "cervid_analytics"
    CLICKHOUSE_SECURE: str = "false"

    # ── MLflow (required by training/swarm, not serving) ──
    MLFLOW_TRACKING_URI: Optional[str] = None
    MLFLOW_S3_ENDPOINT_URL: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    MLFLOW_EXPERIMENT_NAME: str = "fx-swarm"

    # ── Novita API (required by swarm, not serving/training) ──
    NOVITA_BASE_URL: Optional[str] = None
    NOVITA_API_KEY: Optional[str] = None
    LLM_ANALYSIS_MODEL: str = "qwen/qwen3.5-397b-a17b"
    LLM_ROUTING_MODEL: str = "qwen/qwen3-32b-fp8"
    LLM_EMBEDDING_MODEL: str = "qwen/qwen3-embedding-8b"
    LLM_EMBEDDING_DIM: int = 4096
    LLM_EMBEDDING_BATCH_SIZE: int = 10

    # ── Training Defaults ──
    EPOCHS: int = 50
    OPTUNA_TRIALS: int = 20
    SEQUENCE_LENGTH: int = 60
    TRAIN_WINDOW_MONTHS: int = 8
    VAL_WINDOW_MONTHS: int = 2
    TEST_WINDOW_MONTHS: int = 2
    BATCH_SIZE: int = 64
    EARLY_STOPPING_PATIENCE: int = 10
    LEARNING_RATE_MIN: float = 1e-4
    LEARNING_RATE_MAX: float = 1e-2

    # ── Swarm ──
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "fx_experiments"
    SWARM_BATCH_SIZE: int = 4
    EXPLORATION_BUDGET_PCT: float = 0.20
    CIRCUIT_BREAKER_THRESHOLD: int = 50

    # ── Promotion Gate ──
    MIN_DIRECTIONAL_ACCURACY: float = 0.52
    MIN_OOS_PREDICTIONS: int = 500
    MAX_PBO: float = 0.30
    DSR_IMPROVEMENT_THRESHOLD: float = 0.05
    MAX_DRAWDOWN_TOLERANCE: float = 1.10

    # ── Notifications ──
    DISCORD_WEBHOOK_URL: Optional[str] = None

    # ── Research Crawl (required by swarm only) ──
    TAVILY_API_KEY: Optional[str] = None

    # ── Infrastructure ──
    GPU_NODE_POOL: str = "pool-a1lt1h9r5-gpu-pool"
    CPU_NODE_POOL: str = "ams3-digitalocean-cervid-amd-pool"
    ARGO_NAMESPACE: str = "argo-workflows"
    S3_ARTIFACT_BUCKET: str = "fx-swarm-artifacts"
    DRAGONFLY_URL: str = "redis://dragonfly:6379/0"

    # ── Research Knowledge ──
    QDRANT_RESEARCH_COLLECTION: str = "fx_research"

    # ── Pip Sizes ──
    PIP_SIZES: dict = {
        "USD_JPY": 0.01, "EUR_JPY": 0.01, "GBP_JPY": 0.01,
        "EUR_USD": 0.0001, "GBP_USD": 0.0001, "AUD_USD": 0.0001,
        "USD_CHF": 0.0001, "USD_CAD": 0.0001, "NZD_USD": 0.0001,
    }

    def pip_size(self, pair: str) -> float:
        return self.PIP_SIZES.get(pair, 0.0001)

    class Config:
        env_file = ".env"
        case_sensitive = True
