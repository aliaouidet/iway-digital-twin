"""
Async Repository Layer — Bridges in-memory stores to PostgreSQL.

Provides high-level async CRUD functions for:
  - Sessions + Messages
  - Escalation Tickets
  - AI Corrections
  - Audit Logs  
  - Knowledge Embeddings (pgvector)

All functions accept an AsyncSession from the get_db() dependency.
They operate alongside the in-memory stores during the transition,
so the app works with or without a live database.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy import select, update, func, cast, Date, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    Session as SessionModel,
    Message as MessageModel,
    EscalationTicket,
    AICorrection,
    AuditLog,
    KnowledgeEmbedding,
    SessionStatus,
    MessageRole,
    EscalationPriority,
    CorrectionType,
    SourceType,
)

logger = logging.getLogger("I-Way-Twin")


# ==============================================================
# SESSIONS
# ==============================================================

async def create_session(
    db: AsyncSession,
    session_id: str,
    user_matricule: str,
    reason: Optional[str] = None,
) -> SessionModel:
    """Create a new chat session in PostgreSQL."""
    session = SessionModel(
        id=uuid.UUID(session_id) if isinstance(session_id, str) else session_id,
        user_matricule=user_matricule,
        status=SessionStatus.ACTIVE,
        reason=reason,
    )
    db.add(session)
    await db.flush()
    logger.info(f"💾 Session {session_id} persisted to DB")
    return session


async def update_session_status(
    db: AsyncSession,
    session_id: str,
    status: str,
    agent_matricule: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Update session status (e.g., active → handoff_pending → agent_connected → resolved)."""
    values = {"status": SessionStatus(status)}
    if agent_matricule:
        values["agent_matricule"] = agent_matricule
    if reason:
        values["reason"] = reason
    if status == "resolved":
        values["resolved_at"] = datetime.now(timezone.utc)

    await db.execute(
        update(SessionModel)
        .where(SessionModel.id == uuid.UUID(session_id))
        .values(**values)
    )
    await db.flush()


async def get_session_by_id(db: AsyncSession, session_id: str) -> Optional[SessionModel]:
    """Fetch a session with its messages and escalation ticket."""
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == uuid.UUID(session_id))
    )
    return result.scalar_one_or_none()


async def get_pending_sessions(db: AsyncSession) -> List[SessionModel]:
    """Get all sessions awaiting agent handoff."""
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.status == SessionStatus.HANDOFF_PENDING)
        .order_by(SessionModel.created_at.desc())
    )
    return list(result.scalars().all())


async def get_active_sessions(db: AsyncSession) -> List[SessionModel]:
    """Get all non-resolved sessions."""
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.status != SessionStatus.RESOLVED)
        .order_by(SessionModel.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_sessions(db: AsyncSession, matricule: str) -> List[SessionModel]:
    """Get all sessions for a specific user."""
    result = await db.execute(
        select(SessionModel)
        .where(SessionModel.user_matricule == matricule)
        .order_by(SessionModel.created_at.desc())
    )
    return list(result.scalars().all())


# ==============================================================
# MESSAGES
# ==============================================================

async def save_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    confidence: Optional[float] = None,
    model_used: Optional[str] = None,
) -> MessageModel:
    """Save a chat message to the database."""
    message = MessageModel(
        session_id=uuid.UUID(session_id),
        role=MessageRole(role),
        content=content,
        confidence=confidence,
        model_used=model_used,
    )
    db.add(message)
    await db.flush()
    return message


async def get_session_messages(
    db: AsyncSession, session_id: str, limit: int = 100,
) -> List[MessageModel]:
    """Fetch messages for a session, ordered by timestamp."""
    result = await db.execute(
        select(MessageModel)
        .where(MessageModel.session_id == uuid.UUID(session_id))
        .order_by(MessageModel.timestamp)
        .limit(limit)
    )
    return list(result.scalars().all())


# ==============================================================
# ESCALATION TICKETS
# ==============================================================

async def create_escalation_ticket(
    db: AsyncSession,
    session_id: str,
    priority: str = "medium",
    reason: Optional[str] = None,
) -> EscalationTicket:
    """Create an escalation ticket linked to a session."""
    ticket = EscalationTicket(
        session_id=uuid.UUID(session_id),
        priority=EscalationPriority(priority),
        reason=reason,
        status="open",
    )
    db.add(ticket)
    await db.flush()
    logger.info(f"🎫 Escalation ticket created for session {session_id}")
    return ticket


async def get_open_tickets(db: AsyncSession) -> List[EscalationTicket]:
    """Get all open escalation tickets."""
    result = await db.execute(
        select(EscalationTicket)
        .where(EscalationTicket.status == "open")
        .order_by(EscalationTicket.created_at.desc())
    )
    return list(result.scalars().all())


# ==============================================================
# AI CORRECTIONS
# ==============================================================

async def save_correction(
    db: AsyncSession,
    session_id: str,
    correct_answer: str,
    agent_matricule: str,
    correction_type: str = "factual_error",
    wrong_message_id: Optional[str] = None,
) -> AICorrection:
    """Save an AI correction flagged by an agent."""
    correction = AICorrection(
        session_id=uuid.UUID(session_id),
        wrong_message_id=uuid.UUID(wrong_message_id) if wrong_message_id else None,
        correct_answer=correct_answer,
        agent_matricule=agent_matricule,
        correction_type=CorrectionType(correction_type),
    )
    db.add(correction)
    await db.flush()
    return correction


async def get_all_corrections(db: AsyncSession) -> List[AICorrection]:
    """Get all AI corrections for admin review."""
    result = await db.execute(
        select(AICorrection).order_by(AICorrection.created_at.desc())
    )
    return list(result.scalars().all())


# ==============================================================
# AUDIT LOG (Pipeline Traces)
# ==============================================================

async def save_audit_log(
    db: AsyncSession,
    trace_id: str,
    event_type: str,
    session_id: Optional[str] = None,
    outcome: Optional[str] = None,
    latency_ms: Optional[int] = None,
    model_used: Optional[str] = None,
    confidence: Optional[float] = None,
    tokens_used: Optional[int] = 0,
    events: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Save a pipeline trace to the audit log."""
    log = AuditLog(
        trace_id=trace_id,
        session_id=uuid.UUID(session_id) if session_id else None,
        event_type=event_type,
        outcome=outcome,
        latency_ms=latency_ms,
        model_used=model_used,
        confidence=confidence,
        tokens_used=tokens_used,
        events=events,
    )
    db.add(log)
    await db.flush()
    return log


async def get_recent_audit_logs(
    db: AsyncSession, limit: int = 50,
) -> List[AuditLog]:
    """Get recent audit logs for the monitoring dashboard."""
    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_token_stats(db: AsyncSession) -> Dict[str, Any]:
    """LLM token consumption from the audit log (real usage_metadata counts).

    Durable across restarts — unlike the process-local Prometheus counters.
    Averages only over requests that actually consumed tokens (cache hits and
    RAG-only answers legitimately use none).
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    total = await db.scalar(select(func.coalesce(func.sum(AuditLog.tokens_used), 0)))

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    last_24h = await db.scalar(
        select(func.coalesce(func.sum(AuditLog.tokens_used), 0))
        .where(AuditLog.timestamp >= since)
    )

    llm_requests = await db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.tokens_used > 0)
    )
    avg_per_request = round((total or 0) / llm_requests) if llm_requests else 0

    return {
        "total_tokens": int(total or 0),
        "tokens_24h": int(last_24h or 0),
        "llm_requests": int(llm_requests or 0),
        "avg_tokens_per_llm_request": avg_per_request,
    }


async def get_audit_stats(
    db: AsyncSession,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Get aggregated audit statistics, optionally filtered by date range."""
    from datetime import timedelta

    # Build base filter
    filters = []
    if start_date:
        filters.append(AuditLog.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        # end_date is inclusive — add 1 day
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        filters.append(AuditLog.timestamp < end_dt)

    base_q = select(func.count(AuditLog.id))
    if filters:
        base_q = base_q.where(*filters)
    total = await db.scalar(base_q)
    
    outcomes = {}
    outcome_q = select(AuditLog.outcome, func.count(AuditLog.id)).group_by(AuditLog.outcome)
    if filters:
        outcome_q = outcome_q.where(*filters)
    result = await db.execute(outcome_q)
    for outcome, count in result.all():
        if outcome:
            outcomes[outcome] = count

    latency_q = select(func.avg(AuditLog.latency_ms)).where(AuditLog.latency_ms.isnot(None))
    if filters:
        latency_q = latency_q.where(*filters)
    avg_latency = await db.scalar(latency_q)

    conf_q = select(func.avg(AuditLog.confidence)).where(AuditLog.confidence.isnot(None))
    if filters:
        conf_q = conf_q.where(*filters)
    avg_confidence = await db.scalar(conf_q)

    # Normalize: confidence is stored as 0-1 float → convert to 0-100 percentage
    c = float(avg_confidence or 0)
    c_pct = round(c * 100, 1) if c <= 1.0 else round(c, 1)

    return {
        "total_traces": total or 0,
        "outcomes": outcomes,
        "avg_latency_ms": round(avg_latency or 0),
        "avg_confidence": c_pct,
    }

async def get_audit_time_series(
    db: AsyncSession,
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get daily time-series data for the dashboard, filtered by date range."""
    from datetime import timedelta

    # Build filter from explicit dates or fallback to days
    filters = []
    if start_date:
        filters.append(AuditLog.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        filters.append(AuditLog.timestamp < end_dt)
    if not filters:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filters.append(AuditLog.timestamp >= cutoff)
    
    # Cast timestamp to date for grouping
    date_col = cast(AuditLog.timestamp, Date).label("day")
    
    result = await db.execute(
        select(
            date_col,
            func.avg(AuditLog.latency_ms).label("avg_latency"),
            func.avg(AuditLog.confidence).label("avg_confidence"),
            func.count(AuditLog.id).label("total_traces"),
            func.sum(AuditLog.tokens_used).label("total_tokens")
        )
        .where(*filters)
        .group_by(date_col)
        .order_by(date_col)
    )
    
    series = []
    for row in result.all():
        day_date = row.day
        # Use actual date string for x-axis (e.g., "May 18")
        day_label = day_date.strftime("%b %d") if day_date else "Unk"
        
        # Normalize confidence: stored as 0-1 → convert to 0-100 integer
        c = float(row.avg_confidence or 0)
        c_pct = int(c * 100) if c <= 1.0 else int(c)
        
        series.append({
            "day": day_label,
            "date": str(day_date),
            "rag_confidence": c_pct,
            "response_time": round(row.avg_latency or 0),
            "total_traces": row.total_traces,
            "total_tokens": row.total_tokens or 0
        })
        
    return series


async def get_hourly_traffic(
    db: AsyncSession,
    target_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get hourly query counts for a specific date (defaults to today)."""
    from datetime import timedelta
    
    if target_date:
        day_start = datetime.fromisoformat(target_date)
    else:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    day_end = day_start + timedelta(days=1)
    
    # Extract hour from timestamp
    hour_col = func.extract('hour', AuditLog.timestamp).label("hour")
    
    result = await db.execute(
        select(
            hour_col,
            func.count(AuditLog.id).label("count")
        )
        .where(AuditLog.timestamp >= day_start, AuditLog.timestamp < day_end)
        .group_by(hour_col)
        .order_by(hour_col)
    )
    
    # Build a full 24h array, filling gaps with 0
    hour_counts = {int(row.hour): row.count for row in result.all()}
    return [
        {"hour": h, "label": f"{h:02d}:00", "count": hour_counts.get(h, 0)}
        for h in range(24)
    ]

# ==============================================================
# KNOWLEDGE EMBEDDINGS (pgvector)
# ==============================================================

async def upsert_knowledge_embedding(
    db: AsyncSession,
    source_id: str,
    source_type: str,
    chunk_text: str,
    embedding: List[float],
    metadata: Optional[Dict[str, Any]] = None,
) -> KnowledgeEmbedding:
    """Upsert a knowledge embedding into pgvector."""
    # Check if exists
    existing = await db.execute(
        select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.source_id == source_id,
            KnowledgeEmbedding.source_type == SourceType(source_type),
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.chunk_text = chunk_text
        record.embedding = embedding
        record.metadata_ = metadata
        record.last_synced_at = datetime.now(timezone.utc)
    else:
        record = KnowledgeEmbedding(
            source_id=source_id,
            source_type=SourceType(source_type),
            chunk_text=chunk_text,
            embedding=embedding,
            metadata_=metadata,
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(record)

    await db.flush()
    return record


async def get_knowledge_stats_db(db: AsyncSession) -> Dict[str, Any]:
    """Get knowledge store stats from PostgreSQL."""
    total = await db.scalar(select(func.count(KnowledgeEmbedding.id)))
    
    by_type = {}
    result = await db.execute(
        select(KnowledgeEmbedding.source_type, func.count(KnowledgeEmbedding.id))
        .group_by(KnowledgeEmbedding.source_type)
    )
    for stype, count in result.all():
        by_type[stype.value if hasattr(stype, 'value') else str(stype)] = count

    return {
        "total": total or 0,
        "by_source_type": by_type,
    }
