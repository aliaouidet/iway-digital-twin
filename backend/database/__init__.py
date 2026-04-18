# backend/database/__init__.py
from backend.database.connection import engine, async_session_factory, get_db
from backend.database.models import (
    Base, User, Session, Message, EscalationTicket,
    KnowledgeEmbedding, AICorrection, AuditLog,
    UserRole, SessionStatus, MessageRole,
    EscalationPriority, SourceType, CorrectionType,
)
from backend.database import repositories
