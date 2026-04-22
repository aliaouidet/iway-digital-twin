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
from backend.routers.monitoring import router as monitoring_router
from backend.routers.feedback import router as feedback_router
from backend.services.chat_service import handle_chat_websocket
from backend.services.graph_executor import init_claims_graph_async
from backend.services.ws_manager import ConnectionManager

# --- Configuration & Logging ---
settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("I-Way-Twin")

# --- Readiness Gate ---
_app_ready = False

# --- WebSocket Manager (singleton) ---
ws_manager = ConnectionManager()


# --- Lifespan (RSA Key Generation + Graph Init) ---
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

    # --- Claims StateGraph initialization (Phase 5) ---
    logger.info("🧠 Initializing Claims StateGraph...")
    await init_claims_graph_async()

    global _app_ready
    _app_ready = True
    logger.info("✅ Digital Twin Online: Keys Generated, Graph Compiled, Routers Loaded.")
    yield
    # --- Graceful shutdown ---
    _app_ready = False
    try:
        from backend.services.iway_client import close_client
        await close_client()
        logger.info("🔌 I-Way API client closed.")
    except Exception:
        pass
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
app.include_router(monitoring_router)
app.include_router(feedback_router)


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
    """Returns 200 only when the app is fully initialized."""
    if not _app_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "message": "Application is still initializing..."}
        )
    return {"status": "ready", "timestamp": datetime.now().isoformat()}


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
async def chat_websocket(websocket: WebSocket, session_id: str, token: str = None):
    """Per-session WebSocket for user/agent chat.

    Requires JWT auth via query parameter:
      ws://localhost:8000/ws/chat/{session_id}?token={jwt}
    """
    if token:
        try:
            from backend.routers.auth import verify_jwt
            verify_jwt(token)
        except Exception as e:
            await websocket.close(code=4001)
            logger.warning(f"⛔ WebSocket auth failed for session {session_id}: {e}")
            return
    else:
        logger.warning(f"⚠️ WebSocket connection without token for session {session_id} (dev mode)")

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