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

from sqlalchemy import select, update, func
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


async def get_audit_stats(db: AsyncSession) -> Dict[str, Any]:
    """Get aggregated audit statistics."""
    total = await db.scalar(select(func.count(AuditLog.id)))
    
    outcomes = {}
    result = await db.execute(
        select(AuditLog.outcome, func.count(AuditLog.id))
        .group_by(AuditLog.outcome)
    )
    for outcome, count in result.all():
        if outcome:
            outcomes[outcome] = count

    avg_latency = await db.scalar(
        select(func.avg(AuditLog.latency_ms)).where(AuditLog.latency_ms.isnot(None))
    )

    avg_confidence = await db.scalar(
        select(func.avg(AuditLog.confidence)).where(AuditLog.confidence.isnot(None))
    )

    return {
        "total_traces": total or 0,
        "outcomes": outcomes,
        "avg_latency_ms": round(avg_latency or 0),
        "avg_confidence": round((avg_confidence or 0) * 100, 1),
    }


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
