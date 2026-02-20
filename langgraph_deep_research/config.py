"""
Configuration management for LangGraph Deep Research.

Loads API keys from environment variables and configures research parameters.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class Config:
    """Configuration class for API keys and research parameters."""

    # API Keys
    PARALLEL_API_KEY: Optional[str] = os.getenv("PARALLEL_API_KEY")
    NOVITA_API_KEY: Optional[str] = os.getenv("NOVITA_API_KEY")

    # Novita AI Configuration
    NOVITA_BASE_URL: str = "https://api.novita.ai/v3/openai"
    NOVITA_MODEL: str = "qwen/qwen3.5-397b-a17b"  # a17b is the model variant identifier
    NOVITA_TEMPERATURE: float = 0.7
    NOVITA_MAX_TOKENS: int = 2000

    # Parallel AI Configuration
    PARALLEL_PROCESSOR_TYPE: str = "ultra"  # High-quality research processor
    PARALLEL_TIMEOUT: int = 300  # 5 minutes timeout
    PARALLEL_POLL_INTERVAL: int = 5  # Poll every 5 seconds

    # Research Parameters
    MIN_QUESTIONS: int = 3
    MAX_QUESTIONS: int = 5
    MAX_RETRIES: int = 3

    @classmethod
    def validate(cls) -> None:
        """Validate that required API keys are set."""
        if not cls.PARALLEL_API_KEY:
            raise ValueError(
                "PARALLEL_API_KEY environment variable is required. "
                "Please set it in your .env file or environment."
            )
        if not cls.NOVITA_API_KEY:
            raise ValueError(
                "NOVITA_API_KEY environment variable is required. "
                "Please set it in your .env file or environment."
            )

    @classmethod
    def get_novita_config(cls) -> dict:
        """Get Novita AI configuration as a dictionary."""
        return {
            "api_key": cls.NOVITA_API_KEY,
            "base_url": cls.NOVITA_BASE_URL,
            "model": cls.NOVITA_MODEL,
            "temperature": cls.NOVITA_TEMPERATURE,
            "max_tokens": cls.NOVITA_MAX_TOKENS,
        }

    @classmethod
    def get_parallel_config(cls) -> dict:
        """Get Parallel AI configuration as a dictionary."""
        return {
            "api_key": cls.PARALLEL_API_KEY,
            "processor_type": cls.PARALLEL_PROCESSOR_TYPE,
            "timeout": cls.PARALLEL_TIMEOUT,
            "poll_interval": cls.PARALLEL_POLL_INTERVAL,
        }
