"""
Request Tracer — Live pipeline observability for the admin dashboard.

Traces every chat request through the pipeline stages:
  1. RECEIVED    — User message received via WebSocket
  2. RAG_SEARCH  — Embedding + vector similarity search
  3. LLM_EVAL    — Confidence evaluation / LLM response generation
  4. RESPONSE    — AI response streamed back to user
  5. ESCALATED   — Handoff triggered (low confidence / timeout / circuit open)

Each trace captures timing, metadata, and outcome for real-time dashboard display.
"""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("I-Way-Twin")


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

    def finish(self, status: str = "completed", **extra_metadata):
        self.ended_at = time.time()
        self.status = status
        self.metadata.update(extra_metadata)

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

    # Pipeline stages
    spans: List[TraceSpan] = field(default_factory=list)

    # Final outcome
    outcome: Optional[str] = None  # RAG_RESOLVED | AI_FALLBACK | HUMAN_ESCALATED | ERROR | DEGRADED
    confidence: Optional[float] = None
    source_type: Optional[str] = None
    total_duration_ms: Optional[float] = None

    def start_span(self, name: str, **metadata) -> TraceSpan:
        """Start a new pipeline stage."""
        span = TraceSpan(name=name, metadata=metadata)
        self.spans.append(span)
        return span

    def finish(self, outcome: str, confidence: float = None, source_type: str = None):
        """Finalize the trace."""
        self.outcome = outcome
        self.confidence = confidence
        self.source_type = source_type
        self.total_duration_ms = round((time.time() - self.started_at) * 1000, 1)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_matricule": self.user_matricule,
            "query": self.query[:100],  # Truncate for dashboard
            "created_at": self.created_at,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "source_type": self.source_type,
            "total_duration_ms": self.total_duration_ms,
            "spans": [s.to_dict() for s in self.spans],
            "span_count": len(self.spans),
        }


# ==============================================================
# TRACE STORE — In-memory ring buffer of recent traces
# ==============================================================

class TraceStore:
    """
    In-memory trace storage with a configurable ring buffer.
    Keeps the last N traces for dashboard display.
    """

    def __init__(self, max_traces: int = 500):
        self._traces: deque = deque(maxlen=max_traces)
        self._stats = {
            "total_requests": 0,
            "rag_resolved": 0,
            "ai_fallback": 0,
            "human_escalated": 0,
            "errors": 0,
            "degraded": 0,
            "total_duration_ms": 0,
        }

    def add(self, trace: RequestTrace):
        """Add a completed trace."""
        self._traces.appendleft(trace)
        self._stats["total_requests"] += 1
        if trace.total_duration_ms:
            self._stats["total_duration_ms"] += trace.total_duration_ms

        # Update counters
        outcome = trace.outcome or "unknown"
        if outcome == "RAG_RESOLVED":
            self._stats["rag_resolved"] += 1
        elif outcome == "AI_FALLBACK":
            self._stats["ai_fallback"] += 1
        elif outcome == "HUMAN_ESCALATED":
            self._stats["human_escalated"] += 1
        elif outcome == "ERROR":
            self._stats["errors"] += 1
        elif outcome == "DEGRADED":
            self._stats["degraded"] += 1

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Get the most recent traces."""
        return [t.to_dict() for t in list(self._traces)[:limit]]

    def get_stats(self) -> dict:
        """Get aggregated pipeline statistics."""
        total = self._stats["total_requests"]
        avg_duration = (
            round(self._stats["total_duration_ms"] / total, 1)
            if total > 0 else 0
        )
        return {
            "total_requests": total,
            "rag_resolved": self._stats["rag_resolved"],
            "ai_fallback": self._stats["ai_fallback"],
            "human_escalated": self._stats["human_escalated"],
            "errors": self._stats["errors"],
            "degraded": self._stats["degraded"],
            "avg_duration_ms": avg_duration,
            "rag_success_rate": round(
                self._stats["rag_resolved"] / max(total, 1) * 100, 1
            ),
            "escalation_rate": round(
                self._stats["human_escalated"] / max(total, 1) * 100, 1
            ),
            "error_rate": round(
                self._stats["errors"] / max(total, 1) * 100, 1
            ),
        }

    @property
    def count(self) -> int:
        return len(self._traces)


# --- Global trace store ---
trace_store = TraceStore(max_traces=500)


# ==============================================================
# BROADCAST HELPER — Sends traces to WebSocket subscribers
# ==============================================================

_ws_manager_ref = None


def set_trace_ws_manager(ws_manager):
    """Set the WebSocket manager for broadcasting traces."""
    global _ws_manager_ref
    _ws_manager_ref = ws_manager


async def broadcast_trace(trace: RequestTrace):
    """Broadcast a completed trace to all connected admin/agent dashboards."""
    if _ws_manager_ref:
        try:
            await _ws_manager_ref.broadcast({
                "type": "PIPELINE_TRACE",
                "payload": trace.to_dict(),
            })
        except Exception as e:
            logger.error(f"Failed to broadcast trace: {e}")
