import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://iway:iway_secret@localhost:5432/iway_db"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- LLM ---
    USE_LOCAL_LLM: bool = False
    GCP_PROJECT_ID: str = ""
    GCP_LOCATION: str = "us-central1"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "qwen3.5:9b"
    LLM_TIMEOUT_SECONDS: int = 30

    # --- Server ---
    MOCK_SERVER_URL: str = "http://localhost:8000"
    SIMULATE_LATENCY: bool = False

    # --- I-Way Real API ---
    IWAY_USE_REAL_API: bool = False        # False = mock data, True = real I-Way API
    IWAY_API_BASE_URL: str = "http://localhost:8000"  # Override with real URL
    IWAY_API_KEY: str = ""                 # If I-Way uses API key auth

    # --- JWT ---
    JWT_ALGORITHM: str = "RS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # --- RAG ---
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.70
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIMENSIONS: int = 384

    # --- HITL ---
    CONFIDENCE_THRESHOLD: float = 0.30
    HITL_BOOST_FACTOR: float = 1.15
    SESSION_TTL_HOURS: int = 24

    # --- Celery ---
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    SYNC_INTERVAL_MINUTES: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
