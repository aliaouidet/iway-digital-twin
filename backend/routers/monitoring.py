"""
Monitoring Router — Resilience, traces, and knowledge gap endpoints.

Extracted from main.py to follow Clean Architecture routing patterns.
"""

import logging
from collections import defaultdict

from fastapi import APIRouter

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


# --- Pipeline Traces ---
@router.get("/api/v1/traces")
async def get_traces(limit: int = 50):
    """Get recent pipeline traces for the admin dashboard."""
    from backend.services.tracing import trace_store
    return {
        "traces": trace_store.get_recent(limit),
        "count": trace_store.count,
    }


@router.get("/api/v1/traces/stats")
async def get_trace_stats():
    """Get aggregated pipeline metrics — success rates, durations, escalation rates."""
    from backend.services.tracing import trace_store
    from backend.services.rag_service import get_knowledge_stats
    from backend.services.resilience import get_resilience_status

    SESSIONS, ws_manager = _get_sessions_and_manager()
    return {
        "pipeline": trace_store.get_stats(),
        "knowledge": get_knowledge_stats(),
        "resilience": get_resilience_status(),
        "connections": {
            "websocket_count": len(ws_manager.active_connections),
            "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
            "pending_handoffs": len([s for s in SESSIONS.values() if s["status"] == "handoff_pending"]),
        },
    }


# --- Knowledge Gaps ---
@router.get("/api/v1/knowledge/gaps")
async def get_knowledge_gaps():
    """
    Returns questions where AI had low confidence or escalated.
    Admin can use this to identify missing documentation topics.
    """
    from backend.services.tracing import trace_store
    gaps: list[dict] = []
    topic_counts: dict[str, int] = defaultdict(int)

    for trace in trace_store._traces:
        if trace.outcome in ("HUMAN_ESCALATED", "AI_FALLBACK", "DEGRADED") or (
            trace.confidence is not None and trace.confidence < 0.5
        ):
            gaps.append({
                "query": trace.query,
                "confidence": trace.confidence,
                "outcome": trace.outcome,
                "session_id": trace.session_id,
                "timestamp": trace.created_at,
            })
            # Simple keyword extraction for topic clustering
            words = trace.query.lower().split()
            for w in words:
                if len(w) > 4:  # Skip short/common words
                    topic_counts[w] += 1

    # Sort topics by frequency
    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "total_gaps": len(gaps),
        "gaps": gaps[:50],
        "top_missing_topics": [{"topic": t, "count": c} for t, c in top_topics],
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
