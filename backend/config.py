import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://iway:iway_secret@localhost:5432/iway_db"

    # --- Redis ---
    REDIS_URL: str = "redis://:iway_redis_secret@localhost:6379/0"

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

    # --- I-Way Real API (SOAP / Axis2 web services) ---
    # The real I-Way ERP exposes Apache Axis2 SOAP services (not REST). When
    # IWAY_USE_REAL_API is true, personal-record lookups (contrat, remboursements,
    # réclamations, bénéficiaires) are served by backend/services/iway_soap_client.py.
    # NOTE: live calls only succeed on the company LAN; the WSDLs are bundled locally
    # (IWAY_SOAP_WSDL_DIR) so the client builds/validates fully offline.
    IWAY_SOAP_BASE_URL: str = "http://192.168.111.102:8080/axis2/services"
    IWAY_SOAP_WSDL_DIR: str = ""           # Abs path to bundled WSDLs; defaults to <repo>/Webservices
    IWAY_SOAP_LOAD_LOCAL_WSDL: bool = True # Build clients from local WSDL files (offline-safe)
    IWAY_SOAP_USER: str = "admin"          # HTTP Basic auth (Axis2 container)
    IWAY_SOAP_PASSWORD: str = "admin"
    IWAY_SOAP_TIMEOUT: int = 15            # Per-call read timeout (seconds)
    IWAY_SOAP_CONNECT_TIMEOUT: int = 5     # TCP connect timeout — short, so an
                                           # unreachable ERP degrades in seconds, not 30+

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
    CELERY_BROKER_URL: str = "redis://:iway_redis_secret@localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://:iway_redis_secret@localhost:6379/2"
    SYNC_INTERVAL_MINUTES: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
