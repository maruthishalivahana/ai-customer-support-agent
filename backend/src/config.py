"""Centralized configuration management for the Hiver AI Customer Support Agent.

Uses pydantic-settings to validate environment variables from .env files or system env.
"""

from functools import lru_cache
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH if ENV_FILE_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Hiver AI Customer Support Agent"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="Runtime environment: development, testing, production")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR")

    # MongoDB
    MONGODB_URI: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string (local or MongoDB Atlas)",
    )
    MONGODB_DATABASE: str = Field(
        default="hiver_support",
        description="Target MongoDB database name",
    )
    MONGODB_TIMEOUT_MS: int = Field(
        default=2500,
        description="Server selection timeout in milliseconds for health check pings",
    )

    # LLM & OpenRouter Generation Settings (Phase 7)
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="API key for OpenRouter")
    OPENROUTER_MODEL: str = Field(default="openrouter/free", description="Model identifier for OpenRouter generation")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter OpenAI-compatible API base URL",
    )
    OPENROUTER_TIMEOUT_SECONDS: float = Field(
        default=15.0,
        description="HTTP request timeout in seconds for OpenRouter API calls",
    )
    LLM_MAX_GEN_TOKENS: int = Field(
        default=250,
        description="Maximum tokens for generated customer support response",
    )
    LLM_TEMPERATURE: float = Field(
        default=0.2,
        description="Sampling temperature for grounded response generation",
    )
    LLM_API_KEY: Optional[str] = Field(default=None, description="Legacy/alternative LLM API key")
    LLM_MODEL: str = Field(default="openrouter/free", description="Legacy/alternative LLM model identifier")

    # Retrieval & Escalation Policies
    RETRIEVER_TYPE: str = Field(
        default="semantic",
        description="Active default retrieval backend engine: 'semantic' or 'tfidf'",
    )
    EMBEDDING_MODEL: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Lightweight local sentence embedding model",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=128,
        description="Batch size for generating dense embeddings",
    )
    FAISS_INDEX_PATH: Path = Field(
        default_factory=lambda: BASE_DIR / "models" / "semantic_faiss.index",
        description="Path to persisted FAISS vector index",
    )
    FAISS_METADATA_PATH: Path = Field(
        default_factory=lambda: BASE_DIR / "models" / "semantic_faiss_metadata.json",
        description="Path to persisted FAISS index metadata",
    )
    TOP_K_RETRIEVAL: int = Field(default=3, description="Number of historical cases to retrieve")
    MIN_RETRIEVAL_SCORE: float = Field(
        default=0.65,
        description="Minimum similarity score required to consider historical evidence reliable",
    )
    MIN_INTENT_CONFIDENCE: float = Field(
        default=0.70,
        description="Minimum classifier confidence required to avoid human escalation",
    )
    # Decision Engine Policy Parameters (Phase 6)
    INTENT_MIN_CONFIDENCE: float = Field(
        default=0.60,
        description="Initial minimum intent classifier confidence policy parameter",
    )
    RETRIEVAL_MIN_SIMILARITY: float = Field(
        default=0.65,
        description="Initial minimum semantic retrieval similarity threshold for grounding",
    )
    RETRIEVAL_MIN_GAP: float = Field(
        default=0.05,
        description="Initial minimum confidence gap between top candidate intents",
    )
    MAX_TROUBLESHOOTING_ATTEMPTS: int = Field(
        default=2,
        description="Maximum failed troubleshooting turns before escalating to a human specialist",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()


def setup_logging() -> logging.Logger:
    """Configure and return the root application logger."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("hiver_support")
    logger.setLevel(log_level)
    return logger


# Initialize default logger
logger = setup_logging()
