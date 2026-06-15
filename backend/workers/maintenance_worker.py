"""
Maintenance Worker — retention + embedding-lifecycle tasks.

Tasks:
  - prune_old_checkpoints: LangGraph checkpoints grow unbounded (one row per
    super-step per thread, never garbage-collected). This deletes checkpoint
    rows belonging to sessions resolved more than CHECKPOINT_RETENTION_DAYS ago.
  - reembed_knowledge_base: re-embeds every pgvector row with the CURRENT
    embedding model (settings.EMBEDDING_MODEL). Run once after swapping the
    model so the whole vector space stays consistent.
"""

import logging
from datetime import datetime, timezone

from backend.config import get_settings
from backend.workers.celery_app import celery_app

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


def _pg_conn():
    """Plain psycopg2 connection (Celery workers are sync)."""
    import psycopg2
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


@celery_app.task(name="backend.workers.maintenance_worker.prune_old_checkpoints")
def prune_old_checkpoints(retention_days: int = None):
    """Delete LangGraph checkpoints of long-resolved sessions.

    thread_id format is "<matricule>-<session uuid>" (graph_executor), so the
    session uuid is the last 36 chars of the thread_id.
    """
    days = retention_days or settings.CHECKPOINT_RETENTION_DAYS
    deleted = {}
    try:
        conn = _pg_conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    cur.execute(
                        f"""
                        DELETE FROM {table} t
                        USING sessions s
                        WHERE right(t.thread_id, 36) = s.id::text
                          AND s.status = 'resolved'
                          AND s.created_at < NOW() - INTERVAL '%s days'
                        """,
                        (days,),
                    )
                    deleted[table] = cur.rowcount
                except Exception as e:
                    # Table may not exist (MemorySaver fallback) — not an error.
                    conn.rollback() if not conn.autocommit else None
                    deleted[table] = f"skipped ({e.__class__.__name__})"
        conn.close()
        logger.info(f"[Maintenance] Checkpoint prune (> {days}d resolved): {deleted}")
        return {"status": "ok", "deleted": deleted, "retention_days": days}
    except Exception as e:
        logger.warning(f"[Maintenance] Checkpoint prune failed: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name="backend.workers.maintenance_worker.expire_stale_sessions")
def expire_stale_sessions(retention_days: int = None):
    """Auto-expire unresolved sessions older than the retention window.

    Sessions that were escalated (or left active) and never resolved otherwise
    linger forever: hydrate_all_sessions() reloads them on every restart, so the
    agent queue and the dashboard's open_tickets count keep inflating with stale
    demo/abandoned conversations. Marking them 'expired' drops them out of
    get_active_sessions() (which excludes EXPIRED) without deleting any history.
    """
    days = settings.STALE_SESSION_DAYS if retention_days is None else retention_days
    try:
        conn = _pg_conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sessions
                SET status = 'expired'
                WHERE status IN ('active', 'handoff_pending', 'agent_connected')
                  AND created_at < NOW() - INTERVAL '%s days'
                """,
                (days,),
            )
            expired = cur.rowcount
        conn.close()
        logger.info(f"[Maintenance] Expired {expired} stale session(s) (> {days}d unresolved)")
        return {"status": "ok", "expired": expired, "retention_days": days}
    except Exception as e:
        logger.warning(f"[Maintenance] Stale-session expiry failed: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name="backend.workers.maintenance_worker.reembed_knowledge_base", time_limit=3600, soft_time_limit=3300)
def reembed_knowledge_base(batch_size: int = 100):
    """Re-embed every pgvector row with the current embedding model.

    Needed after changing settings.EMBEDDING_MODEL — vectors from different
    models live in incompatible spaces, so similarity scores silently degrade
    unless everything is re-embedded together. Stamps each row's cmetadata
    with embedding_model + embedded_at for auditability.
    """
    from backend.services.rag_service import embed_texts
    import json as _json

    model = settings.EMBEDDING_MODEL
    stamped_at = datetime.now(timezone.utc).isoformat()
    total = 0
    try:
        conn = _pg_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT uuid, document FROM langchain_pg_embedding")
            rows = cur.fetchall()

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            vectors = embed_texts([doc or "" for (_id, doc) in batch])
            with conn.cursor() as cur:
                for (_id, _doc), vec in zip(batch, vectors):
                    cur.execute(
                        """
                        UPDATE langchain_pg_embedding
                        SET embedding = %s::vector,
                            cmetadata = COALESCE(cmetadata, '{}'::jsonb)
                                        || %s::jsonb
                        WHERE uuid = %s
                        """,
                        (str(vec), _json.dumps({"embedding_model": model, "embedded_at": stamped_at}), _id),
                    )
            conn.commit()
            total += len(batch)
            logger.info(f"[Maintenance] Re-embedded {total}/{len(rows)} rows...")

        conn.close()
        logger.info(f"[Maintenance] Re-embed complete: {total} rows on model '{model}'")
        return {"status": "ok", "reembedded": total, "model": model}
    except Exception as e:
        logger.error(f"[Maintenance] Re-embed failed after {total} rows: {e}")
        return {"status": "error", "error": str(e), "reembedded": total}
