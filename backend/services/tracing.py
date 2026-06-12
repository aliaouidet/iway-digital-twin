"""
Request Tracer — Live pipeline observability for the admin dashboard.

Traces every chat request through the pipeline stages:
  1. RECEIVED    — User message received via WebSocket
  2. RAG_SEARCH  — Embedding + vector similarity search
  3. LLM_EVAL    — Confidence evaluation / LLM response generation
  4. RESPONSE    — AI response streamed back to user
  5. ESCALATED   — Handoff triggered (low confidence / timeout / circuit open)

Architecture:
  - PostgreSQL `audit_log` is the SINGLE SOURCE OF TRUTH for all metrics.
  - The in-memory ring buffer exists ONLY for the live trace feed (waterfall view).
  - WebSocket broadcasts individual traces for real-time UI updates.
  - All dashboard KPIs, charts, and analytics read from PostgreSQL.
"""

import uuid
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("I-Way-Twin")


# ==============================================================
# OTEL BRIDGE — mirror business spans into OpenTelemetry/Jaeger
#
# Before this bridge, Jaeger only saw the auto-instrumented HTTP/Redis/DB
# calls (and the chat hot path lives inside one long-lived WebSocket, so it
# saw almost nothing). Each RequestTrace now opens a NEW OTel trace
# ("chat.message") and every TraceSpan becomes a child span — Jaeger shows
# the full business waterfall (decompose → rag → draft → compliance)
# interleaved with the Redis/DB spans captured while it is attached.
# ==============================================================
try:
    from opentelemetry import trace as _otel_api
    from opentelemetry import context as _otel_ctx
    from opentelemetry.context import Context as _OtelContext
    from opentelemetry.trace import set_span_in_context, format_trace_id
    from opentelemetry.trace import Status as _OtelStatus, StatusCode as _OtelStatusCode
    _otel_tracer = _otel_api.get_tracer("iway.pipeline")
    _OTEL = True
except ImportError:  # pragma: no cover — telemetry is optional
    _OTEL = False


def _safe_attrs(metadata: dict) -> dict:
    """OTel attributes must be flat primitives — coerce and truncate."""
    out = {}
    for k, v in (metadata or {}).items():
        if v is None:
            continue
        if isinstance(v, (bool, int, float)):
            out[k] = v
        else:
            out[k] = str(v)[:200]
    return out


# ==============================================================
# TRACE SPAN — A single pipeline stage
# ==============================================================

@dataclass
class TraceSpan:
    """A single step in the request pipeline."""
    name: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"  # running | completed | failed
    _otel_span: Any = field(default=None, repr=False, compare=False)

    def finish(self, status: str = "completed", **extra_metadata):
        self.ended_at = time.time()
        self.status = status
        self.metadata.update(extra_metadata)
        if self._otel_span is not None:
            try:
                for k, v in _safe_attrs(self.metadata).items():
                    self._otel_span.set_attribute(k, v)
                if status == "failed":
                    self._otel_span.set_status(_OtelStatus(_OtelStatusCode.ERROR))
                self._otel_span.end()
            except Exception:
                pass
            self._otel_span = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.ended_at:
            return round((self.ended_at - self.started_at) * 1000, 1)
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


# ==============================================================
# REQUEST TRACE — Full pipeline trace for one user message
# ==============================================================

@dataclass
class RequestTrace:
    """Complete trace for a single user message through the pipeline."""
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:8]}")
    session_id: str = ""
    user_matricule: str = ""
    query: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: float = field(default_factory=time.time)
    otel_trace_id: Optional[str] = None

    # Pipeline stages
    spans: List[TraceSpan] = field(default_factory=list)

    # Final outcome
    outcome: Optional[str] = None  # RAG_RESOLVED | AI_FALLBACK | HUMAN_ESCALATED | ERROR | DEGRADED
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    total_duration_ms: Optional[float] = None
    tokens_used: int = 0

    # OTel mirror (per-message root span + the context-attach token)
    _otel_root: Any = field(default=None, repr=False, compare=False)
    _otel_token: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not _OTEL:
            return
        try:
            # context=Context() forces a NEW trace per user message — otherwise
            # every message in a WS connection would pile into one giant trace.
            self._otel_root = _otel_tracer.start_span(
                "chat.message",
                context=_OtelContext(),
                attributes=_safe_attrs({
                    "session.id": self.session_id,
                    "user.matricule": self.user_matricule,
                    "query.preview": self.query[:80],
                }),
            )
            self.otel_trace_id = format_trace_id(self._otel_root.get_span_context().trace_id)
            # Attach so auto-instrumented Redis/DB spans during this message's
            # processing join OUR trace. attach/detach happen in the same WS
            # task (create → finish), so this is contextvar-safe.
            self._otel_token = _otel_ctx.attach(set_span_in_context(self._otel_root))
        except Exception:
            self._otel_root = None
            self._otel_token = None

    def start_span(self, name: str, **metadata) -> TraceSpan:
        """Start a new pipeline stage."""
        span = TraceSpan(name=name, metadata=metadata)
        if self._otel_root is not None:
            try:
                span._otel_span = _otel_tracer.start_span(
                    name,
                    context=set_span_in_context(self._otel_root),
                    attributes=_safe_attrs(metadata),
                )
            except Exception:
                pass
        self.spans.append(span)
        return span

    def finish(self, outcome: str, confidence: float = None, source_type: str = None):
        """Finalize the trace."""
        self.outcome = outcome
        self.confidence = confidence
        self.source_type = source_type
        self.total_duration_ms = round((time.time() - self.started_at) * 1000, 1)
        # Keep an explicitly-set token count (real LLM usage from graph_executor);
        # fall back to the legacy per-span sum otherwise.
        if not self.tokens_used:
            self.tokens_used = sum(span.metadata.get("tokens", 0) for span in self.spans)

        if self._otel_root is not None:
            try:
                self._otel_root.set_attribute("outcome", outcome or "")
                if confidence is not None:
                    self._otel_root.set_attribute("confidence", float(confidence))
                if source_type:
                    self._otel_root.set_attribute("source.type", source_type)
                self._otel_root.set_attribute("tokens.used", int(self.tokens_used or 0))
                if outcome == "ERROR":
                    self._otel_root.set_status(_OtelStatus(_OtelStatusCode.ERROR))
                self._otel_root.end()
            except Exception:
                pass
            self._otel_root = None
        if self._otel_token is not None:
            try:
                _otel_ctx.detach(self._otel_token)
            except Exception:
                pass
            self._otel_token = None

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "otel_trace_id": self.otel_trace_id,
            "session_id": self.session_id,
            "user_matricule": self.user_matricule,
            "query": self.query[:100],  # Truncate for dashboard
            "created_at": self.created_at,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "source_type": self.source_type,
            "total_duration_ms": self.total_duration_ms,
            "tokens_used": self.tokens_used,
            "spans": [s.to_dict() for s in self.spans],
            "span_count": len(self.spans),
        }


# ==============================================================
# TRACE STORE — In-memory ring buffer for LIVE FEED ONLY
# ==============================================================

class TraceStore:
    """
    Lightweight ring buffer for the live trace feed (waterfall view).

    This is NOT the source of truth for metrics. All KPIs, charts, and
    analytics are computed from PostgreSQL via `repositories.py`.
    This buffer exists solely so the admin can see the last N traces
    in the real-time log viewer without hitting the database.
    """

    def __init__(self, max_traces: int = 500):
        self._traces: deque = deque(maxlen=max_traces)

    def add(self, trace: RequestTrace):
        """Add a completed trace to the live feed buffer."""
        self._traces.appendleft(trace)

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Get the most recent traces for the live log viewer."""
        return [t.to_dict() for t in list(self._traces)[:limit]]

    @property
    def count(self) -> int:
        return len(self._traces)


# --- Global trace store (live feed only) ---
trace_store = TraceStore(max_traces=500)


# ==============================================================
# PERSISTENCE — Writes traces to PostgreSQL (source of truth)
# ==============================================================

_audit_queue = asyncio.Queue()

async def persist_trace(trace: RequestTrace):
    """Enqueue a completed trace to be persisted to PostgreSQL in batches."""
    _audit_queue.put_nowait(trace)

async def audit_worker():
    """Background worker that pulls traces from the queue and batch-inserts them."""
    from backend.database.connection import async_session_factory
    from backend.database.repositories import save_audit_log

    logger.info("🛠️ Started Audit Log Queue Worker")
    while True:
        try:
            batch = []
            while not _audit_queue.empty() and len(batch) < 50:
                batch.append(_audit_queue.get_nowait())
            
            if batch:
                async with async_session_factory() as db:
                    for trace in batch:
                        await save_audit_log(
                            db=db,
                            trace_id=trace.trace_id,
                            event_type="user_query",
                            session_id=trace.session_id if trace.session_id else None,
                            outcome=trace.outcome,
                            latency_ms=round(trace.total_duration_ms) if trace.total_duration_ms else None,
                            model_used=trace.source_type,
                            confidence=trace.confidence,
                            tokens_used=trace.tokens_used,
                            events={
                                "otel_trace_id": trace.otel_trace_id,
                                "query": trace.query[:200],
                                "spans": [s.to_dict() for s in trace.spans],
                            },
                        )
                    await db.commit()
            
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Audit worker error: {e}")
            await asyncio.sleep(2)


# ==============================================================
# BROADCAST — Sends individual traces to WebSocket subscribers
# ==============================================================

_ws_manager_ref = None


def set_trace_ws_manager(ws_manager):
    """Set the WebSocket manager for broadcasting traces."""
    global _ws_manager_ref
    _ws_manager_ref = ws_manager


async def broadcast_trace(trace: RequestTrace):
    """Broadcast a completed trace to all connected admin/agent dashboards
    and persist it to PostgreSQL for durability."""
    # Persist to DB (source of truth)
    try:
        await persist_trace(trace)
    except Exception:
        pass

    # Broadcast individual trace to WebSocket subscribers
    # (the frontend uses these for the live log feed, NOT for KPI computation)
    if _ws_manager_ref:
        try:
            await _ws_manager_ref.broadcast({
                "type": "PIPELINE_TRACE",
                "payload": trace.to_dict(),
            }, target_roles={"Agent", "Admin"})
        except Exception as e:
            logger.error(f"Failed to broadcast trace: {e}")
