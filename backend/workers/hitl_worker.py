"""
HITL Feedback Worker — Re-embed agent-validated Q&A pairs.

When a human agent corrects an AI response, this worker:
1. Embeds the corrected Q&A pair using sentence-transformers
2. Upserts into PGVector with source_type="hitl_validated" + boost factor
3. Invalidates any cached response for the original question

Celery best practices (celery-expert skill):
- bind=True: access self.request for task metadata
- acks_late=True: don't ack until task completes (resilience)
- ignore_result=True: fire-and-forget, no result stored in Redis
- time_limit/soft_time_limit: prevent zombie tasks
- max_retries=3 with exponential backoff
"""

import logging

from backend.workers.celery_app import celery_app
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


@celery_app.task(
    name="backend.workers.hitl_worker.embed_hitl_feedback",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
    time_limit=60,
    soft_time_limit=45,
)
def embed_hitl_feedback(self, session_id: str, question: str, corrected_answer: str,
                        agent_matricule: str = "system", agent_name: str = "Agent",
                        corrected_from: str = None):
    """
    Celery task: Re-embed agent-validated Q&A pair into the RAG knowledge base.

    Args:
        session_id: Chat session where the correction was made
        question: Original user question
        corrected_answer: Agent's corrected response
        agent_matricule: Agent who provided the correction
        agent_name: Agent display name

    Pipeline:
        1. Upsert Q+A into knowledge store (PGVector or in-memory)
        2. Invalidate cache for the original question
    """
    try:
        from backend.services.rag_service import add_hitl_knowledge

        logger.info(
            f"[HITL] Embedding feedback from session {session_id}: "
            f"Q='{question[:50]}...' A='{corrected_answer[:50]}...'"
        )

        # 1. Upsert into knowledge store (uses existing embed + PGVector flow).
        #    origin="correction" marks provenance; corrected_from kept for audit.
        result = add_hitl_knowledge(
            session_id=session_id,
            question=question,
            answer=corrected_answer,
            agent_matricule=agent_matricule,
            agent_name=agent_name,
            origin="correction",
            tags=["correction"],
        )
        if corrected_from:
            logger.info(f"[HITL] Correction supersedes wrong answer: '{corrected_from[:60]}'")

        logger.info(f"[HITL] ✅ Feedback embedded: {result}")

        # 2. Invalidate cache for this question
        _invalidate_cache_sync(question)

        return result

    except Exception as exc:
        logger.error(f"[HITL] ❌ Feedback embedding failed: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


def _invalidate_cache_sync(question: str):
    """Synchronous cache invalidation (runs in Celery worker thread).
    """
    try:
        import asyncio
        from backend.services.semantic_cache import invalidate_semantic_cache
        # Celery workers don't have a running event loop for this simple task usually,
        # so we spin one up just for invalidation.
        asyncio.run(invalidate_semantic_cache(question))
    except Exception as e:
        logger.debug(f"[HITL] Cache invalidation skipped: {e}")
