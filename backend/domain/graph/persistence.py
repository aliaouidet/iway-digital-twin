"""
Persistence Layer — PostgresSaver for production checkpointing.

Provides:
  - get_postgres_checkpointer():  Creates and initializes AsyncPostgresSaver
  - _build_postgres_uri():        Builds psycopg3-compatible connection URI

Uses psycopg3 (async), NOT asyncpg/SQLAlchemy.
"""

import os
import logging

logger = logging.getLogger("I-Way-Twin")


# PostgresSaver — production-grade persistence (Phase 4)
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    _POSTGRES_AVAILABLE = True
except ImportError:
    _POSTGRES_AVAILABLE = False


def _build_postgres_uri() -> str:
    """Construct a psycopg3-compatible connection URI from env vars.

    IMPORTANT: psycopg3 uses 'postgresql://' scheme (NOT 'postgresql+asyncpg://').
    """
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "iway")
    db_pass = os.getenv("DB_PASS", "iway_secret")
    db_name = os.getenv("DB_NAME", "iway_db")

    uri = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    return uri


async def get_postgres_checkpointer() -> "AsyncPostgresSaver":
    """Create and initialize the production PostgreSQL checkpointer.

    Uses an async connection pool (psycopg_pool.AsyncConnectionPool).

    Returns:
        An initialized AsyncPostgresSaver ready for graph compilation.
    """
    if not _POSTGRES_AVAILABLE:
        raise RuntimeError(
            "langgraph-checkpoint-postgres is not installed. "
            "Run: pip install 'psycopg[binary,pool]' langgraph-checkpoint-postgres"
        )

    uri = _build_postgres_uri()
    logger.info(f"Connecting PostgresSaver to: {uri.split('@')[1]}")

    checkpointer = AsyncPostgresSaver.from_conn_string(uri)
    await checkpointer.setup()  # Idempotent — creates tables if they don't exist

    logger.info("PostgresSaver initialized (tables verified)")
    return checkpointer
