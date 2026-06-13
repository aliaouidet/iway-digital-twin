"""
Startup migrations — tiny, additive-only, idempotent.

The repo has no migration tool (schema comes from init.sql, which only runs on
a FRESH Postgres volume). Existing deployments therefore never see columns
added to init.sql. This module closes that gap with `ADD COLUMN IF NOT EXISTS`
statements executed best-effort from the FastAPI lifespan.

Rules:
  * Additive-only (new nullable columns / defaults). NEVER drop or rewrite.
  * Idempotent — safe to run at every startup.
  * Best-effort — a failure is logged, never blocks startup (mirrors session
    hydration / pgvector index ensure in main.py).
"""

import logging

from sqlalchemy import text

logger = logging.getLogger("I-Way-Twin")

_STATEMENTS = [
    # Real-ERP identity columns on users (activation flow, 2026-06)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS num_police VARCHAR(30)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS id_tiers VARCHAR(30)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'mock'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ",
]


async def run_startup_migrations() -> bool:
    """Apply the additive migrations. Returns True when all statements ran."""
    try:
        from backend.database.connection import async_session_factory

        async with async_session_factory() as db:
            for stmt in _STATEMENTS:
                await db.execute(text(stmt))
            await db.commit()
        logger.info(f"🗄️ Startup migrations applied ({len(_STATEMENTS)} statements)")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Startup migrations failed (non-critical, will retry next boot): {e}")
        return False
