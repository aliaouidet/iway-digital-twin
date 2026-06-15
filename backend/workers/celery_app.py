"""
Celery application for I-Way Digital Twin background tasks.

Tasks:
- sync_knowledge: Pull from I-Way mock API → chunk → embed → upsert
- generate_llm_response: Heavy LLM inference offloaded from the event loop
- embed_hitl_response: Embed agent-validated Q&A pairs
"""

import os

from celery import Celery
from backend.config import get_settings

settings = get_settings()


# --- OpenTelemetry for workers (guarded — takes effect after an image rebuild) ---
# Without this, KB syncs / re-embeds / checkpoint prunes were invisible to Jaeger.
try:
    from celery.signals import worker_process_init

    @worker_process_init.connect(weak=False)
    def _init_otel(*args, **kwargs):
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.instrumentation.celery import CeleryInstrumentor

            provider = TracerProvider(resource=Resource.create({"service.name": "iway-worker"}))
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
                endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317"),
                insecure=True,
            )))
            trace.set_tracer_provider(provider)
            CeleryInstrumentor().instrument()
        except Exception:
            pass  # telemetry must never break the worker
except ImportError:  # pragma: no cover
    pass

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
    "backend.workers.maintenance_worker",
]


# --- Periodic Tasks (Celery Beat) ---
celery_app.conf.beat_schedule = {
    "sync-iway-knowledge": {
        "task": "backend.workers.sync_worker.sync_knowledge_base",
        "schedule": settings.SYNC_INTERVAL_MINUTES * 60,  # Convert to seconds
        "options": {"queue": "default"},
    },
    # Nightly retention: LangGraph checkpoints of long-resolved sessions are
    # pruned so the checkpoint tables don't grow unbounded.
    "prune-old-checkpoints": {
        "task": "backend.workers.maintenance_worker.prune_old_checkpoints",
        "schedule": 24 * 3600,
        "options": {"queue": "default"},
    },
    # Nightly: unresolved sessions older than STALE_SESSION_DAYS are expired so
    # the agent queue + dashboard open_tickets don't accumulate abandoned cases.
    "expire-stale-sessions": {
        "task": "backend.workers.maintenance_worker.expire_stale_sessions",
        "schedule": 24 * 3600,
        "options": {"queue": "default"},
    },
}
