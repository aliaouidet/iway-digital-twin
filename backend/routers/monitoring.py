"""
Monitoring Router — Resilience, traces, and knowledge gap endpoints.

Architecture:
  - PostgreSQL is the SINGLE SOURCE OF TRUTH for all analytics.
  - The in-memory trace_store ring buffer is used ONLY for the live
    trace feed (real-time waterfall view in the admin panel).
  - All aggregated stats (KPIs, rates) are computed from PostgreSQL.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db
from backend.database.repositories import get_audit_stats

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(tags=["Monitoring"])


def _get_sessions_and_manager():
    """Lazy import to avoid circular dependencies."""
    from backend.routers.sessions import SESSIONS
    from main import ws_manager
    return SESSIONS, ws_manager


# --- Resilience Status ---
@router.get("/api/v1/resilience")
async def resilience_status():
    """Get detailed resilience status — circuit breakers, fallback state."""
    from backend.services.resilience import get_resilience_status
    from backend.services.rag_service import get_knowledge_stats

    SESSIONS, ws_manager = _get_sessions_and_manager()
    return {
        **get_resilience_status(),
        "knowledge": get_knowledge_stats(),
        "active_ws_connections": len(ws_manager.active_connections),
        "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
        "pending_handoffs": len([s for s in SESSIONS.values() if s["status"] == "handoff_pending"]),
    }


# --- Pipeline Traces (live feed from ring buffer) ---
@router.get("/api/v1/traces")
async def get_traces(limit: int = 50):
    """Get recent pipeline traces for the live waterfall viewer.
    
    Uses the in-memory ring buffer for instant response.
    This is NOT used for analytics — just for the live log feed.
    """
    from backend.services.tracing import trace_store
    return {
        "traces": trace_store.get_recent(limit),
        "count": trace_store.count,
    }


# --- Pipeline Stats (from PostgreSQL) ---
@router.get("/api/v1/traces/stats")
async def get_trace_stats(db: AsyncSession = Depends(get_db)):
    """Aggregated pipeline metrics from PostgreSQL — the single source of truth.
    
    Returns success rates, durations, escalation rates, knowledge stats,
    and connection information.
    """
    from backend.services.rag_service import get_knowledge_stats
    from backend.services.resilience import get_resilience_status

    # All metrics from PostgreSQL
    stats = await get_audit_stats(db)
    
    total = stats.get("total_traces", 0)
    outcomes = stats.get("outcomes", {})
    
    rag_resolved = outcomes.get("RAG_RESOLVED", 0) + outcomes.get("GRAPH_RESOLVED", 0) + outcomes.get("STALL_RESOLVED", 0)
    ai_fallback = outcomes.get("AI_FALLBACK", 0)
    human_escalated = outcomes.get("HUMAN_ESCALATED", 0)
    errors = outcomes.get("ERROR", 0)

    SESSIONS, ws_manager = _get_sessions_and_manager()
    return {
        "pipeline": {
            "total_requests": total,
            "rag_resolved": rag_resolved,
            "agent_resolved": outcomes.get("AGENT_RESOLVED", 0),
            "ai_fallback": ai_fallback,
            "human_escalated": human_escalated,
            "errors": errors,
            "degraded": outcomes.get("DEGRADED", 0),
            "avg_duration_ms": stats.get("avg_latency_ms", 0),
            "rag_success_rate": round(rag_resolved / max(total, 1) * 100, 1),
            "agent_success_rate": round(outcomes.get("AGENT_RESOLVED", 0) / max(total, 1) * 100, 1),
            "escalation_rate": round(human_escalated / max(total, 1) * 100, 1),
            "error_rate": round(errors / max(total, 1) * 100, 1),
        },
        "knowledge": get_knowledge_stats(),
        "resilience": get_resilience_status(),
        "connections": {
            "websocket_count": len(ws_manager.active_connections),
            "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
            "pending_handoffs": len([s for s in SESSIONS.values() if s["status"] == "handoff_pending"]),
        },
    }


# --- Knowledge Gaps (from PostgreSQL) ---
@router.get("/api/v1/knowledge/gaps")
async def get_knowledge_gaps():
    """
    Returns questions where AI had low confidence or escalated.
    Uses Gemini-powered clustering for professional topic identification.
    
    Data source: PostgreSQL audit_log (single source of truth).
    """
    from backend.services.insights_service import cluster_failed_queries
    from backend.database.connection import async_session_factory

    gaps: list[dict] = []

    try:
        async with async_session_factory() as db:
            from backend.database.repositories import get_recent_audit_logs
            db_logs = await get_recent_audit_logs(db, limit=500)

            for log_record in db_logs:
                c = log_record.confidence
                c_norm = (float(c) / 100.0 if float(c) > 1.0 else float(c)) if c is not None else None

                if log_record.outcome in ("HUMAN_ESCALATED", "AI_FALLBACK", "DEGRADED") or (
                    c_norm is not None and c_norm < 0.5
                ):
                    query = log_record.events.get("query", "") if log_record.events else ""
                    if query:
                        gaps.append({
                            "query": query,
                            "confidence": c_norm,
                            "outcome": log_record.outcome,
                            "session_id": str(log_record.session_id) if log_record.session_id else "",
                            "timestamp": log_record.timestamp.isoformat() if log_record.timestamp else "",
                        })
    except Exception as e:
        logger.error(f"Knowledge gaps DB read failed: {e}")
        # No fallback — PostgreSQL is the single source of truth
        return {"total_gaps": 0, "gaps": [], "top_missing_topics": [], "error": str(e)}

    # Use Gemini clustering for proper topic identification
    clustering = await cluster_failed_queries(gaps)

    return {
        "total_gaps": len(gaps),
        "gaps": gaps[:50],
        "top_missing_topics": [
            {"topic": t.topic, "count": t.query_count, "priority": t.priority}
            for t in clustering.topics
        ],
    }


# --- Real-Time Analytics (Redis Counters) ---
@router.get("/api/v1/stats/realtime")
async def get_realtime_stats():
    """
    Real-time analytics from Redis atomic counters.
    O(1) reads — no trace scanning, no DB queries.

    Returns: queries_today, escalations, cache_hits, unique_users,
             avg_confidence, top_intents, cache_hit_rate.
    """
    from backend.services.analytics import get_realtime_stats
    return await get_realtime_stats()
