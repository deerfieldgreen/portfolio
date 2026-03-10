"""Configuration management using pydantic-settings.

All settings loaded from environment variables (Doppler-managed).
No defaults for sensitive values — fail fast if missing.
"""
from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Economic Calendar Agent settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # FMP API Configuration
    fmp_api_key: SecretStr
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"
    fmp_rate_limit_per_min: int = 750  # Premium tier

    # ClickHouse Configuration
    clickhouse_url: str = "localhost"
    clickhouse_port: int = 443
    clickhouse_database: str = "cervid_analytics"
    clickhouse_username: str = "cervid"
    clickhouse_password: SecretStr = SecretStr("")

    # Dragonfly Configuration (Redis-compatible)
    dragonfly_endpoint: str = "localhost"
    dragonfly_port: int = 6379
    dragonfly_username: str = "default"
    dragonfly_password: SecretStr = SecretStr("")

    # Qdrant Configuration
    qdrant_endpoint: str = "localhost"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "economic_events"

    # Novita LLM Configuration
    novita_api_key: SecretStr
    novita_base_url: str = "https://api.novita.ai/openai"
    novita_llm_model: str = "qwen/qwen3.5-397b-a17b"
    novita_llm_temperature: float = 0.1
    novita_llm_max_tokens: int = 2000

    # Embedding Configuration
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimension: int = 768

    # Trading Pairs Configuration
    target_pairs: list[str] = ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"]

    # Pipeline Configuration
    pipeline_lookback_days: int = 90  # How far back to fetch events
    pipeline_lookahead_hours: int = 48  # How far ahead to analyze

    # Cache Configuration
    cache_ttl_seconds: int = 36000  # 10 hours default, matches Cervid convention

    @property
    def dragonfly_url(self) -> str:
        """Build Redis-compatible connection URL from Dragonfly params."""
        password = self.dragonfly_password.get_secret_value()
        username = self.dragonfly_username
        host = self.dragonfly_endpoint
        port = self.dragonfly_port
        if password:
            return f"redis://{username}:{password}@{host}:{port}/0"
        return f"redis://{host}:{port}/0"


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
