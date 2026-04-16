"""
Sync Worker — Pulls knowledge from I-Way mock API, embeds, and upserts.

This runs:
  - As a Celery periodic task (every 5 minutes via beat schedule)
  - On-demand via REST API trigger
  - At startup (initial sync)
"""

import logging
import httpx

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
    1. Fetch knowledge_base entries from I-Way mock API
    2. Embed using sentence-transformers (all-MiniLM-L6-v2)
    3. Upsert into the vector store
    """
    try:
        from backend.services.rag_service import sync_knowledge_from_api

        # Fetch from I-Way mock API
        api_url = f"{settings.MOCK_SERVER_URL}/api/v1/knowledge-base"
        logger.info(f"[SyncWorker] Fetching knowledge from {api_url}")

        response = httpx.get(api_url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])

        if not items:
            logger.warning("[SyncWorker] No knowledge items received")
            return {"status": "empty", "synced": 0}

        # Sync (embed + upsert)
        result = sync_knowledge_from_api(items)
        logger.info(f"[SyncWorker] Sync complete: {result}")
        return result

    except httpx.HTTPError as e:
        logger.error(f"[SyncWorker] API fetch failed: {e}")
        self.retry(exc=e)
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
