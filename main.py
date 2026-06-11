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

from backend.config import get_settings
from backend.routers.auth import router as auth_router, auth_state
from backend.routers.iway_mock import router as iway_router, MOCK_ESCALATION_TICKETS
from backend.routers.sessions import router as sessions_router, SESSIONS, set_ws_manager
from backend.routers.dashboard import router as dashboard_router
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
    # Load (or generate-and-persist) the RSA keypair. Persisting means an API
    # restart no longer invalidates every live JWT (previously keys were
    # regenerated per process, logging everyone out on each deploy/reload).
    from backend.routers.auth import init_keys
    loaded = init_keys(settings.JWT_KEYS_DIR)
    logger.info(f"🔐 RSA keypair {'loaded from' if loaded else 'generated into'} {settings.JWT_KEYS_DIR}")
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

    # --- Restore ALL non-resolved sessions from PostgreSQL ---
    # Without this, an API restart silently emptied the agent escalation queue:
    # handoff_pending users stayed stranded until they sent another message.
    from backend.services.session_store import hydrate_all_sessions
    await hydrate_all_sessions()

    # --- Ensure pgvector ANN index (idempotent) ---
    # Without an HNSW index, similarity search on langchain_pg_embedding is a
    # sequential scan — fine at 1k chunks, painful at 100k+.
    try:
        from sqlalchemy import text as _sql
        from backend.database.connection import async_session_factory
        dims = settings.EMBEDDING_DIMENSIONS
        async with async_session_factory() as db:
            # langchain_postgres creates the column as dimensionless `vector`;
            # HNSW requires fixed dims — type it first (no-op once applied).
            await db.execute(_sql(
                f"ALTER TABLE langchain_pg_embedding "
                f"ALTER COLUMN embedding TYPE vector({dims}) USING embedding::vector({dims})"
            ))
            await db.execute(_sql(
                "CREATE INDEX IF NOT EXISTS langchain_embedding_hnsw_idx "
                "ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)"
            ))
            await db.commit()
        logger.info(f"📐 pgvector HNSW index ensured (vector({dims}))")
    except Exception as e:
        logger.warning(f"⚠️ pgvector HNSW index skipped (table may not exist yet): {e}")

    # --- Semantic router warm-up ---
    # The router embeds its ~100 exemplar utterances lazily on first use, which
    # costs ~30s on CPU — warm it here so the first user message isn't the one
    # paying for it.
    try:
        import anyio
        from backend.domain.graph.semantic_router import classify_intent
        await anyio.to_thread.run_sync(classify_intent, "bonjour")
        logger.info("🧭 Semantic router warmed up (exemplar embeddings cached)")
    except Exception as e:
        logger.warning(f"⚠️ Semantic router warm-up failed (non-critical): {e}")

    # --- Redis connection pool (caching + analytics) ---
    try:
        from backend.services.redis_client import get_redis
        await get_redis()
    except Exception as e:
        logger.warning(f"⚠️ Redis pool init failed (non-critical): {e}")

    # --- Start Audit Worker ---
    from backend.services.tracing import audit_worker
    audit_task = asyncio.create_task(audit_worker())

    global _app_ready
    _app_ready = True
    logger.info("✅ Digital Twin Online: Keys Generated, Graph Compiled, Routers Loaded.")
    yield
    # --- Graceful shutdown ---
    _app_ready = False
    audit_task.cancel()
    try:
        from backend.services.redis_client import close_redis
        await close_redis()
    except Exception:
        pass
    try:
        from backend.services.iway_client import close_client
        await close_client()
        logger.info("🔌 I-Way API client closed.")
    except Exception:
        pass
    try:
        from backend.services.iway_soap_client import close_soap_clients
        await close_soap_clients()
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

# --- OpenTelemetry Instrumentation ---
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    # Setup tracing provider
    resource = Resource.create({"service.name": "iway-digital-twin"})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317", insecure=True))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument external dependencies (Redis & PostgreSQL)
    RedisInstrumentor().instrument()
    PsycopgInstrumentor().instrument()
    
    logger.info("🔭 OpenTelemetry (Jaeger) instrumentation enabled.")
except ImportError:
    logger.warning("⚠️ OpenTelemetry not installed. Tracing disabled.")

# CORS: explicit origins come from settings.ALLOWED_ORIGINS (comma-separated env
# var) — in production that list is the ONLY source. The wide private-LAN regex
# is a development convenience (open the app at any LAN IP without per-IP edits)
# and is disabled when ENVIRONMENT=production.
_cors_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
_dev_lan_regex = (
    r"http://(localhost|127\.0\.0\.1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}):(4200|8000)"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=(None if settings.ENVIRONMENT == "production" else _dev_lan_regex),
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
        "auth": "POST /auth/login with {matricule, password}",
        "docs": "/docs"
    }


# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Docker Compose and monitoring."""
    from backend.services.rag_service import get_knowledge_count
    from backend.services.resilience import llm_circuit, embedding_circuit, api_circuit, CircuitState
    from backend.services.persistence_health import get_persistence_health

    # Check circuit breaker health
    circuits_healthy = all(
        cb.state != CircuitState.OPEN
        for cb in [llm_circuit, embedding_circuit, api_circuit]
    )

    kb = get_knowledge_count()
    persistence = get_persistence_health()
    healthy = circuits_healthy and not persistence["degraded"]
    return {
        "status": "healthy" if healthy else "degraded",
        "services": {
            "api": "up",
            "knowledge_store": f"{kb['total']} entries ({kb['store']})",
            "llm_circuit": llm_circuit.state.value,
            "embedding_circuit": embedding_circuit.state.value,
            "websocket_connections": len(ws_manager.active_connections),
        },
        "persistence": persistence,
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


# --- WebSocket auth handshake ---
async def _ws_authenticate(websocket: WebSocket, token: str | None, require_roles=None):
    """Accept the socket and authenticate.

    Preferred protocol: the client's FIRST frame is {"type": "auth", "token": jwt}
    — tokens in query strings leak into proxy logs / browser history. The legacy
    ?token= query param is still honored for backward compatibility.

    Returns {"matricule", "role"} on success; closes the socket and returns None
    on failure. The socket is ACCEPTED either way (callers must not re-accept).
    """
    from backend.routers.auth import verify_jwt, MOCK_USERS

    await websocket.accept()

    if not token:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            frame = json.loads(raw)
            if str(frame.get("type", "")).lower() != "auth":
                await websocket.close(code=4001)
                return None
            token = frame.get("token") or (frame.get("payload") or {}).get("token")
        except Exception:
            await websocket.close(code=4001)
            return None

    try:
        payload = verify_jwt(token)
    except Exception:
        await websocket.close(code=4001)
        return None

    matricule = payload.get("sub")
    user = MOCK_USERS.get(matricule, {})
    role = user.get("role", "Adherent")
    if require_roles and role not in require_roles:
        await websocket.close(code=4003)
        logger.warning(f"⛔ WebSocket rejected: role '{role}' not authorized")
        return None
    return {"matricule": matricule, "role": role}


# --- Admin/Agent events WebSocket ---
@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time dashboard/agent updates.

    Auth: first-frame {"type":"auth","token":...} (or legacy ?token=).
    Only Agent/Admin roles allowed.
    """
    auth = await _ws_authenticate(websocket, token, require_roles=("Agent", "Admin"))
    if not auth:
        return

    await ws_manager.connect(websocket, role=auth["role"], matricule=auth["matricule"], accepted=True)
    try:
        while True:
            from backend.database.connection import async_session_factory
            from backend.database.repositories import get_audit_stats
            
            async with async_session_factory() as db:
                stats = await get_audit_stats(db)
                outcomes = stats.get("outcomes", {})
                
            pending_sessions = sum(1 for s in SESSIONS.values() if s["status"] == "handoff_pending")
            await websocket.send_json({
                "type": "METRIC_UPDATE",
                "payload": {
                    "total_requests": stats.get("total_traces", 0),
                    "rag_resolved": outcomes.get("RAG_RESOLVED", 0),
                    "ai_fallback": outcomes.get("AI_FALLBACK", 0),
                    "human_escalated": outcomes.get("HUMAN_ESCALATED", 0),
                    "errors": outcomes.get("ERROR", 0),
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

    Auth: first-frame {"type":"auth","token":...} (or legacy ?token= during the
    transition — query-string tokens leak into proxy logs).
    """
    auth = await _ws_authenticate(websocket, token)
    if not auth:
        logger.warning(f"⛔ Chat WebSocket auth failed for session {session_id}")
        return

    await handle_chat_websocket(websocket, session_id, SESSIONS, ws_manager, accepted=True)


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