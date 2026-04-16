import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime,
    ForeignKey, Enum as SAEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector
from backend.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# --- Enums ---

class UserRole(str, enum.Enum):
    ADHERENT = "Adherent"
    PRESTATAIRE = "Prestataire"
    AGENT = "Agent"
    ADMIN = "Admin"


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    HANDOFF_PENDING = "handoff_pending"
    AGENT_CONNECTED = "agent_connected"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"
    SYSTEM = "system"


class EscalationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(str, enum.Enum):
    IWAY_API = "iway_api"
    HITL_VALIDATED = "hitl_validated"


class CorrectionType(str, enum.Enum):
    FACTUAL_ERROR = "factual_error"
    OUTDATED = "outdated"
    HALLUCINATION = "hallucination"
    INCOMPLETE = "incomplete"


# --- Models ---

class User(Base):
    __tablename__ = "users"

    matricule = Column(String(20), primary_key=True)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.ADHERENT)
    email = Column(String(255), nullable=True)
    specialite = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)  # Plain text for mock, bcrypt in prod
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = relationship("Session", back_populates="user", foreign_keys="Session.user_matricule")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_matricule = Column(String(20), ForeignKey("users.matricule"), nullable=False)
    agent_matricule = Column(String(20), ForeignKey("users.matricule"), nullable=True)
    status = Column(SAEnum(SessionStatus), nullable=False, default=SessionStatus.ACTIVE)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions", foreign_keys=[user_matricule])
    agent = relationship("User", foreign_keys=[agent_matricule])
    messages = relationship("Message", back_populates="session", order_by="Message.timestamp")
    escalation_ticket = relationship("EscalationTicket", back_populates="session", uselist=False)

    __table_args__ = (
        Index("ix_sessions_status", "status"),
        Index("ix_sessions_user", "user_matricule"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(SAEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    model_used = Column(String(50), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("Session", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session", "session_id"),
        Index("ix_messages_timestamp", "timestamp"),
    )


class EscalationTicket(Base):
    __tablename__ = "escalation_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, unique=True)
    priority = Column(SAEnum(EscalationPriority), nullable=False, default=EscalationPriority.MEDIUM)
    reason = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="open")
    assigned_agent = Column(String(20), ForeignKey("users.matricule"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    session = relationship("Session", back_populates="escalation_ticket")

    __table_args__ = (
        Index("ix_escalation_status", "status"),
    )


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(100), nullable=False)
    source_type = Column(SAEnum(SourceType), nullable=False, default=SourceType.IWAY_API)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)  # Renamed to avoid Python conflict
    last_synced_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_knowledge_source", "source_id", "source_type", unique=True),
    )


class AICorrection(Base):
    __tablename__ = "ai_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    wrong_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    correct_answer = Column(Text, nullable=False)
    agent_matricule = Column(String(20), ForeignKey("users.matricule"), nullable=False)
    correction_type = Column(SAEnum(CorrectionType), nullable=False, default=CorrectionType.FACTUAL_ERROR)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(String(100), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    outcome = Column(String(30), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    model_used = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    events = Column(JSONB, nullable=True)  # Full trace event chain
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_audit_session", "session_id"),
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_trace", "trace_id"),
    )
