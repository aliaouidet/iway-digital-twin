"""
Sync Worker — Pulls knowledge from I-Way mock API, embeds, and upserts.

This runs:
  - As a Celery periodic task (every 5 minutes via beat schedule)
  - On-demand via REST API trigger
  - At startup (initial sync)
"""

import logging

from backend.workers.celery_app import celery_app
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


@celery_app.task(
    name="backend.workers.sync_worker.sync_knowledge_base",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_knowledge_base(self):
    """
    Celery task: Sync pipeline.
    1. Fetch knowledge entries (from real I-Way API or mock data)
    2. Embed using sentence-transformers (all-MiniLM-L6-v2)
    3. Upsert into the vector store
    
    Toggle: Set IWAY_USE_REAL_API=true to fetch from the real API.
    """
    try:
        from backend.services.rag_service import sync_knowledge_from_api

        if settings.IWAY_USE_REAL_API:
            # Real API — fetch via HTTP (sync since we're in a Celery worker)
            import httpx
            resp = httpx.get(
                f"{settings.IWAY_API_BASE_URL}/api/v1/knowledge-base",
                headers={"X-API-Key": settings.IWAY_API_KEY} if settings.IWAY_API_KEY else {},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            logger.info(f"[SyncWorker] Fetched {len(items)} items from real API")
        else:
            # Mock data — direct import (no network dependency)
            from backend.routers.iway_mock import MOCK_KB
            items = MOCK_KB

        if not items:
            logger.warning("[SyncWorker] No knowledge items available")
            return {"status": "empty", "synced": 0}

        # Sync (embed + upsert)
        result = sync_knowledge_from_api(items)
        logger.info(f"[SyncWorker] Sync complete: {result}")
        return result

    except Exception as exc:
        logger.error(f"[SyncWorker] Unexpected error: {exc}")
        self.retry(exc=exc)


def sync_knowledge_direct():
    """
    Direct sync (non-Celery) — for startup and on-demand API calls.
    Called from main.py lifespan or from the REST API.
    """
    from backend.services.rag_service import sync_knowledge_from_api
    from backend.routers.iway_mock import MOCK_KB

    # Use the in-process mock data directly (no HTTP call needed)
    result = sync_knowledge_from_api(MOCK_KB)
    return result
