"""
Celery application for I-Way Digital Twin background tasks.

Tasks:
- sync_knowledge: Pull from I-Way mock API → chunk → embed → upsert
- generate_llm_response: Heavy LLM inference offloaded from the event loop
- embed_hitl_response: Embed agent-validated Q&A pairs
"""

from celery import Celery
from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "iway_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_time_limit=120,       # Hard kill after 2 minutes
    task_soft_time_limit=90,   # Raise SoftTimeLimitExceeded after 90s
    
    # Result backend (redis-development/ram-ttl rule)
    result_expires=3600,       # Auto-cleanup results after 1 hour
    
    # Worker
    worker_prefetch_multiplier=1,  # Fair scheduling for GPU tasks
    worker_max_tasks_per_child=50, # Recycle workers to prevent memory leaks
    
    # Retry
    task_acks_late=True,           # Don't ack until task completes (resilience)
    task_reject_on_worker_lost=True,
)

# Explicit task module registration (autodiscover can miss tasks in Docker)
celery_app.conf.include = [
    "backend.workers.sync_worker",
    "backend.workers.hitl_worker",
]


# --- Periodic Tasks (Celery Beat) ---
celery_app.conf.beat_schedule = {
    "sync-iway-knowledge": {
        "task": "backend.workers.sync_worker.sync_knowledge_base",
        "schedule": settings.SYNC_INTERVAL_MINUTES * 60,  # Convert to seconds
        "options": {"queue": "default"},
    },
}
