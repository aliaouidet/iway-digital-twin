"""
I-Way Digital Twin — Main Application Entry Point

This is the orchestrator. It:
1. Initializes RSA keys for JWT signing
2. Registers all modular routers
3. Hosts WebSocket endpoints (events + per-session chat)
4. Configures CORS middleware

All business logic lives in backend/routers/ and backend/services/.
"""

import json
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from backend.config import get_settings
from backend.routers.auth import router as auth_router, auth_state
from backend.routers.iway_mock import router as iway_router, MOCK_ESCALATION_TICKETS
from backend.routers.sessions import router as sessions_router, SESSIONS, set_ws_manager
from backend.routers.dashboard import router as dashboard_router, SYSTEM_LOGS
from backend.routers.knowledge import router as knowledge_router
from backend.routers.corrections import router as corrections_router
from backend.services.chat_service import handle_chat_websocket

# --- Configuration & Logging ---
settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("I-Way-Twin")

# --- Readiness Gate ---
_app_ready = False


# --- Lifespan (RSA Key Generation) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔐 Generating RSA 2048-bit Key Pair...")
    auth_state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth_state.public_key_pem = auth_state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    # Inject WebSocket manager into sessions router
    set_ws_manager(ws_manager)

    # Inject WebSocket manager into tracing service
    from backend.services.tracing import set_trace_ws_manager
    set_trace_ws_manager(ws_manager)

    # --- Initial knowledge sync (embed mock KB into vector store) ---
    try:
        from backend.workers.sync_worker import sync_knowledge_direct
        result = sync_knowledge_direct()
        logger.info(f"📚 Initial knowledge sync: {result['total']} entries embedded")
    except Exception as e:
        logger.warning(f"⚠️ Initial knowledge sync failed (non-critical): {e}")

    global _app_ready
    _app_ready = True
    logger.info("✅ Digital Twin Online: Keys Generated & Routers Loaded.")
    yield
    _app_ready = False
    logger.info("🛑 Digital Twin Shutting Down.")


# --- FastAPI App ---
app = FastAPI(
    title="I-Way Digital Twin API",
    description="Enterprise HITL Claims Management Platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:4201",
        "http://iway-frontend:4200",  # Docker container name
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers ---
app.include_router(auth_router)
app.include_router(iway_router)
app.include_router(sessions_router)
app.include_router(dashboard_router)
app.include_router(knowledge_router)
app.include_router(corrections_router)


# --- WebSocket Manager ---
class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()


# --- System Root ---
@app.get("/", tags=["System"])
async def root():
    return {
        "system": "I-Way Digital Twin",
        "version": "2.0.0",
        "architecture": "modular",
        "status": "operational",
        "personas_available": [
            "12345 / pass   (Nadia – Adherent)",
            "99999 / med    (Dr. Amine – Prestataire)",
            "88888 / agent  (Karim – Agent)",
            "77777 / admin  (Sara – Admin)",
        ],
        "auth": "POST /auth/login with {matricule, password}",
        "docs": "/docs"
    }


# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker Compose and monitoring."""
    from backend.services.rag_service import knowledge_store
    from backend.services.resilience import llm_circuit, embedding_circuit, api_circuit, CircuitState

    # Check circuit breaker health
    circuits_healthy = all(
        cb.state != CircuitState.OPEN
        for cb in [llm_circuit, embedding_circuit, api_circuit]
    )

    return {
        "status": "healthy" if circuits_healthy else "degraded",
        "services": {
            "api": "up",
            "knowledge_store": f"{knowledge_store.count} entries",
            "llm_circuit": llm_circuit.state.value,
            "embedding_circuit": embedding_circuit.state.value,
            "websocket_connections": len(ws_manager.active_connections),
        },
        "timestamp": datetime.now().isoformat()
    }


# --- Readiness Probe (for Docker/K8s startup checks) ---
@app.get("/ready", tags=["System"])
async def readiness_probe():
    """Returns 200 only when the app is fully initialized (keys + model + knowledge loaded)."""
    if not _app_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "message": "Application is still initializing..."}
        )
    return {"status": "ready", "timestamp": datetime.now().isoformat()}


# --- CSAT Feedback ---
_feedback_store: list[dict] = []

@app.post("/api/v1/sessions/{session_id}/feedback", tags=["Sessions"])
async def submit_feedback(session_id: str, body: dict):
    """
    Submit CSAT feedback after session resolved.
    Body: { rating: 'positive' | 'negative', comment?: string }
    """
    if session_id not in SESSIONS:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    rating = body.get("rating", "positive")
    comment = body.get("comment", "")
    feedback = {
        "session_id": session_id,
        "rating": rating,
        "comment": comment,
        "timestamp": datetime.now().isoformat(),
    }
    _feedback_store.append(feedback)
    SESSIONS[session_id]["feedback"] = feedback
    logger.info(f"📊 CSAT feedback for {session_id}: {rating}")
    return {"status": "received", "rating": rating}


@app.get("/api/v1/feedback/stats", tags=["Monitoring"])
async def feedback_stats():
    """Get aggregated CSAT stats for the admin dashboard."""
    total = len(_feedback_store)
    positive = sum(1 for f in _feedback_store if f["rating"] == "positive")
    negative = sum(1 for f in _feedback_store if f["rating"] == "negative")
    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "csat_score": round(positive / max(total, 1) * 100, 1),
        "recent": _feedback_store[-10:],
    }


# --- Knowledge Gaps ---
@app.get("/api/v1/knowledge/gaps", tags=["Monitoring"])
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


# --- Resilience Status ---
@app.get("/api/v1/resilience", tags=["Monitoring"])
async def resilience_status():
    """Get detailed resilience status — circuit breakers, fallback state."""
    from backend.services.resilience import get_resilience_status
    from backend.services.rag_service import get_knowledge_stats
    return {
        **get_resilience_status(),
        "knowledge": get_knowledge_stats(),
        "active_ws_connections": len(ws_manager.active_connections),
        "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
        "pending_handoffs": len([s for s in SESSIONS.values() if s["status"] == "handoff_pending"]),
    }


# --- Pipeline Traces ---
@app.get("/api/v1/traces", tags=["Monitoring"])
async def get_traces(limit: int = 50):
    """Get recent pipeline traces for the admin dashboard."""
    from backend.services.tracing import trace_store
    return {
        "traces": trace_store.get_recent(limit),
        "count": trace_store.count,
    }


@app.get("/api/v1/traces/stats", tags=["Monitoring"])
async def get_trace_stats():
    """Get aggregated pipeline metrics — success rates, durations, escalation rates."""
    from backend.services.tracing import trace_store
    from backend.services.rag_service import get_knowledge_stats
    from backend.services.resilience import get_resilience_status
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


# --- Admin/Agent events WebSocket ---
@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard/agent updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            logs = SYSTEM_LOGS
            total = len(logs)
            rag_resolved = sum(1 for l in logs if l["outcome"] == "RAG_RESOLVED")
            pending_sessions = sum(1 for s in SESSIONS.values() if s["status"] == "handoff_pending")
            await websocket.send_json({
                "type": "METRIC_UPDATE",
                "payload": {
                    "total_requests": total,
                    "rag_resolved": rag_resolved,
                    "ai_fallback": sum(1 for l in logs if l["outcome"] == "AI_FALLBACK"),
                    "human_escalated": sum(1 for l in logs if l["outcome"] == "HUMAN_ESCALATED"),
                    "errors": sum(1 for l in logs if l["outcome"] == "ERROR"),
                    "open_tickets": len(MOCK_ESCALATION_TICKETS),
                    "pending_handoffs": pending_sessions,
                    "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
                    "timestamp": datetime.now().isoformat(),
                }
            })
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# --- Per-session chat WebSocket ---
@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """Per-session WebSocket for user/agent chat."""
    await handle_chat_websocket(websocket, session_id, SESSIONS, ws_manager)


# --- Entry Point ---
if __name__ == "__main__":
    import uvicorn
    print("\n[INFO] I-Way Digital Twin v2.0 — Modular Architecture")
    print(f"   Persona 1 (Adherent):     matricule=12345  password=pass")
    print(f"   Persona 2 (Prestataire):  matricule=99999  password=med")
    print(f"   Persona 3 (Agent):        matricule=88888  password=agent")
    print(f"   Persona 4 (Admin):        matricule=77777  password=admin")
    print(f"   Docs available at: http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)