"""
Dashboard Router — Monitoring, analytics, and admin configuration.

Routes:
  GET  /api/v1/metrics
  GET  /api/v1/logs
  GET  /api/v1/insights
  GET  /api/v1/admin/config
  PUT  /api/v1/admin/config
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import get_db
from backend.database.repositories import get_audit_stats, get_recent_audit_logs, get_audit_time_series, get_hourly_traffic

from backend.routers.auth import get_current_user, require_role

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1", tags=["Monitoring"])


# --- Persistent admin config (in-memory, survives requests) ---

SYSTEM_CONFIG = {
    "rag": {
        "chunking_strategy": "semantic",
        "top_k": 3,
        "similarity_threshold": 82,
        "enable_ai_fallback": True,
        "auto_escalate_negative_sentiment": True,
    },
    "llm": {
        "primary_model": "gemini-2.5-flash",
        "temperature": 0.2,
        "system_prompt": "Tu es l'assistant virtuel I-Sante...",
    },
    "retry": {
        "max_retries": 3,
        "backoff_seconds": 2,
    },
}


# --- Pydantic Models ---

class ConfigUpdate(BaseModel):
    rag: Optional[Dict[str, Any]] = None
    llm: Optional[Dict[str, Any]] = None
    retry: Optional[Dict[str, Any]] = None



# --- Helpers ---



def _get_sessions():
    """Lazy import SESSIONS dict."""
    from backend.routers.sessions import SESSIONS
    return SESSIONS


# --- Endpoints ---

@router.get("/metrics", tags=["Monitoring"])
async def get_metrics(
    days: int = Query(7, description="Number of days for time-series data"),
    start_date: Optional[str] = Query(None, description="Start date filter (yyyy-MM-dd)"),
    end_date: Optional[str] = Query(None, description="End date filter (yyyy-MM-dd)"),
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(get_current_user)
):
    """Aggregated dashboard metrics from PostgreSQL — fully date-filtered."""
    stats = await get_audit_stats(db, start_date=start_date, end_date=end_date)
    
    # Get time-series data with the same date filters
    time_series = await get_audit_time_series(db, days=days, start_date=start_date, end_date=end_date)
    
    try:
        sessions = _get_sessions()
        open_tickets = len([s for s in sessions.values() if s.get("status") == "handoff_pending"])
    except Exception:
        open_tickets = 0

    total = stats.get("total_traces", 0)
    outcomes = stats.get("outcomes", {})
    
    rag_resolved = outcomes.get("RAG_RESOLVED", 0) + outcomes.get("GRAPH_RESOLVED", 0)
    ai_fallback = outcomes.get("AI_FALLBACK", 0)
    human_escalated = outcomes.get("HUMAN_ESCALATED", 0)
    errors = outcomes.get("ERROR", 0)

    # ── Period-over-period comparison (previous equal-length window) ──
    # Only meaningful when a bounded range is active; "All Time" has no "before".
    # Lets the dashboard show ▲/▼ deltas vs the immediately preceding window.
    comparison = None
    if start_date and end_date:
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d").date()
            e = datetime.strptime(end_date, "%Y-%m-%d").date()
            window = (e - s).days + 1
            if window >= 1:
                prev_end = s - timedelta(days=1)
                prev_start = prev_end - timedelta(days=window - 1)
                prev = await get_audit_stats(
                    db, start_date=prev_start.isoformat(), end_date=prev_end.isoformat()
                )
                p_total = prev.get("total_traces", 0)
                p_out = prev.get("outcomes", {})
                p_rag = p_out.get("RAG_RESOLVED", 0) + p_out.get("GRAPH_RESOLVED", 0)
                p_human = p_out.get("HUMAN_ESCALATED", 0)
                comparison = {
                    "total_requests": p_total,
                    "rag_success_rate": round(p_rag / max(p_total, 1) * 100, 1),
                    "escalation_rate": round(p_human / max(p_total, 1) * 100, 1),
                    "avg_confidence": prev.get("avg_confidence", 0),
                    "avg_response_time_ms": prev.get("avg_latency_ms", 0),
                    "window_days": window,
                }
        except (ValueError, TypeError):
            comparison = None

    return {
        "total_requests": total,
        "rag_resolved": rag_resolved,
        "agent_resolved": 0,
        "ai_fallback": ai_fallback,
        "human_escalated": human_escalated,
        "errors": errors,
        "degraded": 0,
        "avg_confidence": stats.get("avg_confidence", 0),
        "avg_response_time_ms": stats.get("avg_latency_ms", 0),
        "rag_success_rate": round(rag_resolved / max(total, 1) * 100, 1),
        "agent_success_rate": 0,
        "fallback_rate": round(ai_fallback / max(total, 1) * 100, 1),
        "escalation_rate": round(human_escalated / max(total, 1) * 100, 1),
        "error_rate": round(errors / max(total, 1) * 100, 1),
        "degraded_rate": 0,
        "open_tickets": open_tickets,
        "time_series": time_series,
        "comparison": comparison,
    }


@router.get("/metrics/traffic", tags=["Monitoring"])
async def get_traffic(
    date: Optional[str] = Query(None, description="Target date for hourly traffic (yyyy-MM-dd)"),
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(get_current_user)
):
    """Hourly traffic heatmap data for a specific date."""
    hourly = await get_hourly_traffic(db, target_date=date)
    return {"hourly": hourly, "date": date or "today"}


@router.get("/logs", tags=["Monitoring"])
async def get_logs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    outcome: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_similarity: Optional[float] = Query(None, ge=0, le=1),
    start_date: Optional[str] = Query(None, description="Start date filter (yyyy-MM-dd)"),
    end_date: Optional[str] = Query(None, description="End date filter (yyyy-MM-dd)"),
    matricule: str = Depends(get_current_user),
):
    """Paginated system logs from PostgreSQL."""
    # We fetch a large enough limit to do in-memory filtering for now
    # In a full prod environment, these filters should be pushed to the database query
    db_logs = await get_recent_audit_logs(db, limit=1000)

    # Normalize confidence to 0.0-1.0 range (since some nodes return 0-100)
    def norm_conf(c):
        val = float(c or 0)
        return val / 100.0 if val > 1.0 else val

    # Convert traces to log-format dicts
    logs = []
    for log_record in db_logs:
        conf = norm_conf(log_record.confidence)
        
        # Extract total tokens from span metadata if available
        spans = log_record.events.get("spans", []) if log_record.events else []
        total_tokens = sum(span.get("metadata", {}).get("tokens", 0) for span in spans)
        
        # Extract actual similarity and chunks retrieved from metadata
        chunks_count = 0
        top_sim = conf
        for span in spans:
            meta = span.get("metadata", {})
            if "retrieved_docs" in meta and isinstance(meta["retrieved_docs"], list):
                chunks_count = max(chunks_count, len(meta["retrieved_docs"]))
            if "similarity" in meta and meta["similarity"] is not None:
                top_sim = norm_conf(meta["similarity"])
                
        # Fallback for older traces where metadata might not have retrieved_docs
        if chunks_count == 0 and log_record.outcome in ["RAG_RESOLVED", "GRAPH_RESOLVED"]:
            chunks_count = 3
        
        # If no tokens found but it was resolved, estimate from latency
        if total_tokens == 0 and (log_record.latency_ms or 0) > 1000:
            total_tokens = int((log_record.latency_ms / 1000) * 12)
            
        log = {
            "id": log_record.trace_id,
            "otel_trace_id": log_record.events.get("otel_trace_id") if log_record.events else None,
            "timestamp": log_record.timestamp.isoformat() if log_record.timestamp else "",
            "user_id": log_record.session_id or "unknown",
            "query": log_record.events.get("query", "") if log_record.events else "",
            "top_similarity": top_sim,
            "chunks_retrieved": chunks_count,
            "gen_time_ms": round(log_record.latency_ms or 0),
            "tokens_used": total_tokens,
            "outcome": log_record.outcome or "UNKNOWN",
            "model": log_record.model_used or "gemini-2.5-flash",
            "confidence": conf,
            "spans": spans,
        }
        logs.append(log)

    # Apply filters
    if outcome:
        logs = [l for l in logs if l["outcome"] == outcome]
    if user_id:
        logs = [l for l in logs if l["user_id"] == user_id]
    if search:
        q = search.lower()
        logs = [l for l in logs if q in l["query"].lower() or q in l["user_id"].lower()]
    if min_similarity is not None:
        logs = [l for l in logs if l["top_similarity"] >= min_similarity]
    # ISO timestamps sort lexically, so a yyyy-MM-dd prefix compare is enough.
    if start_date:
        logs = [l for l in logs if l["timestamp"] and l["timestamp"][:10] >= start_date]
    if end_date:
        logs = [l for l in logs if l["timestamp"] and l["timestamp"][:10] <= end_date]

    total = len(logs)
    start = (page - 1) * page_size
    page_logs = logs[start:start + page_size]

    return {
        "items": page_logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/insights", tags=["Analytics"])
async def get_insights(
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(get_current_user)
):
    """AI-generated insights from PostgreSQL audit logs with Gemini-powered clustering."""
    from backend.services.insights_service import cluster_failed_queries

    stats = await get_audit_stats(db)
    total = stats.get("total_traces", 0)
    outcomes = stats.get("outcomes", {})
    rag_resolved = outcomes.get("RAG_RESOLVED", 0) + outcomes.get("GRAPH_RESOLVED", 0)
    ai_fallback = outcomes.get("AI_FALLBACK", 0)
    human_escalated = outcomes.get("HUMAN_ESCALATED", 0)

    db_logs = await get_recent_audit_logs(db, limit=500)

    # ── Build confidence distribution from real traces ──
    conf_buckets = {f"{i/10:.1f}-{(i+1)/10:.1f}": 0 for i in range(10)}
    failed_queries = []

    for log_record in db_logs:
        # Confidence distribution
        c = log_record.confidence
        if c is not None:
            c_norm = float(c) / 100.0 if float(c) > 1.0 else float(c)
            bucket_idx = min(int(c_norm * 10), 9)
            key = f"{bucket_idx/10:.1f}-{(bucket_idx+1)/10:.1f}"
            if key in conf_buckets:
                conf_buckets[key] += 1

        # Collect failed/low-confidence queries for Gemini clustering
        if log_record.outcome in ("AI_FALLBACK", "HUMAN_ESCALATED", "DEGRADED") or (
            c is not None and (float(c) / 100.0 if float(c) > 1.0 else float(c)) < 0.5
        ):
            query = log_record.events.get("query", "") if log_record.events else ""
            if query:
                c_val = float(c) / 100.0 if (c and float(c) > 1.0) else float(c or 0)
                failed_queries.append({
                    "query": query,
                    "confidence": c_val,
                    "outcome": log_record.outcome or "UNKNOWN",
                    "timestamp": log_record.timestamp.isoformat() if log_record.timestamp else "",
                    "session_id": str(log_record.session_id) if log_record.session_id else "",
                })

    # ── Gemini-powered topic clustering (with fallback) ──
    clustering = await cluster_failed_queries(failed_queries)

    # Build suggestions from AI clusters
    suggestions = []
    fallback_categories = []
    for topic in clustering.topics:
        suggestions.append({
            "category": topic.topic,
            "count": topic.query_count,
            "trend": "up" if topic.priority in ("critical", "high") else "stable",
            "trend_pct": min(topic.query_count * 8, 60),
            "priority": topic.priority,
            "suggestion": topic.suggestion,
            "sample_queries": topic.sample_queries,
        })
        fallback_categories.append({
            "name": topic.topic,
            "count": topic.query_count,
        })

    confidence_distribution = [
        {"range": k, "count": v} for k, v in conf_buckets.items()
    ]

    return {
        "knowledge_gaps": len(failed_queries),
        "rag_coverage_rate": round(rag_resolved / max(total, 1) * 100),
        "docs_suggested": len([s for s in suggestions if s["priority"] in ("critical", "high")]),
        "failed_clusters": len(clustering.topics),
        "ai_summary": clustering.summary,
        "suggestions": suggestions,
        "fallback_categories": fallback_categories,
        "confidence_distribution": confidence_distribution,
        # Extra stats for the dashboard
        "total_queries": total,
        "total_fallback": ai_fallback,
        "total_escalated": human_escalated,
        "avg_confidence": stats.get("avg_confidence", 0),
    }


@router.get("/admin/config", tags=["Admin"])
async def get_admin_config(matricule: str = Depends(require_role("Admin", "Agent"))):
    return SYSTEM_CONFIG


@router.put("/admin/config", tags=["Admin"])
async def update_admin_config(data: ConfigUpdate, matricule: str = Depends(require_role("Admin"))):
    if data.rag:
        SYSTEM_CONFIG["rag"].update(data.rag)
    if data.llm:
        SYSTEM_CONFIG["llm"].update(data.llm)
    if data.retry:
        SYSTEM_CONFIG["retry"].update(data.retry)
    logger.info(f"Config updated by {matricule}")
    return {"status": "updated", "config": SYSTEM_CONFIG}
