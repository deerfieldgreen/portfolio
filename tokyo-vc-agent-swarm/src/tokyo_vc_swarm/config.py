"""
Configuration management for Tokyo VC Agent Swarm.

Loads API keys and credentials from environment variables,
and non-secret parameters from config.yaml.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_yaml() -> Dict[str, Any]:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


class Config:
    """Centralised configuration for the VC scoring swarm."""

    # Secrets from environment
    NOVITA_API_KEY: Optional[str] = os.getenv("NOVITA_API_KEY")

    CLICKHOUSE_HOST: str = os.getenv("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT: int = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    CLICKHOUSE_USER: str = os.getenv("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DATABASE: str = os.getenv("CLICKHOUSE_DATABASE", "vc_swarm")

    _yaml: Dict[str, Any] = {}

    @classmethod
    def _ensure_yaml(cls) -> None:
        if not cls._yaml:
            cls._yaml = _load_yaml()

    @classmethod
    def validate(cls) -> None:
        """Raise if required secrets are missing."""
        if not cls.NOVITA_API_KEY:
            raise ValueError(
                "NOVITA_API_KEY environment variable is required. "
                "Set it in your environment or via Doppler."
            )

    @classmethod
    def get_novita_config(cls) -> Dict[str, Any]:
        cls._ensure_yaml()
        cfg = cls._yaml.get("novita", {})
        return {
            "api_key": cls.NOVITA_API_KEY,
            "base_url": cfg.get("base_url", "https://api.novita.ai/v3/openai"),
            "model": cfg.get("model", "qwen/qwen3-max"),
            "temperature": cfg.get("temperature", 0.2),
            "max_tokens": cfg.get("max_tokens", 512),
        }

    @classmethod
    def get_dimension_configs(cls) -> Dict[str, Dict[str, Any]]:
        """Return per-dimension weight + invert config from config.yaml."""
        cls._ensure_yaml()
        return cls._yaml.get("dimensions", {})

    @classmethod
    def get_default_weights(cls) -> Dict[str, float]:
        """Return {dimension_name: weight} mapping."""
        return {
            dim: cfg["weight"]
            for dim, cfg in cls.get_dimension_configs().items()
        }

    @classmethod
    def get_inverted_dimensions(cls) -> set:
        """Return set of dimension names where score should be inverted."""
        return {
            dim
            for dim, cfg in cls.get_dimension_configs().items()
            if cfg.get("invert", False)
        }

    @classmethod
    def get_clickhouse_config(cls) -> Dict[str, Any]:
        cls._ensure_yaml()
        tbl = cls._yaml.get("clickhouse", {})
        return {
            "host": cls.CLICKHOUSE_HOST,
            "port": cls.CLICKHOUSE_PORT,
            "username": cls.CLICKHOUSE_USER,
            "password": cls.CLICKHOUSE_PASSWORD,
            "database": cls.CLICKHOUSE_DATABASE,
            "scores_table": tbl.get("scores_table", "deal_scores"),
            "rankings_table": tbl.get("rankings_table", "deal_rankings"),
        }

    @classmethod
    def get_api_config(cls) -> Dict[str, Any]:
        cls._ensure_yaml()
        return cls._yaml.get("api", {"top_k_default": 10, "host": "0.0.0.0", "port": 8000})
