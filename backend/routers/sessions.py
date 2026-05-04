"""
Sessions Router — HITL session lifecycle management with multi-chat support.

Routes:
  POST /api/v1/sessions/create
  GET  /api/v1/sessions/active
  GET  /api/v1/sessions/user-chats        ← Multi-chat: list user's chats
  GET  /api/v1/sessions/{session_id}/history
  GET  /api/v1/sessions/{session_id}/briefing   ← Agent briefing panel
  POST /api/v1/sessions/{session_id}/takeover
  POST /api/v1/sessions/{session_id}/approve    ← Agent approves/clarifies AI response
  POST /api/v1/sessions/{session_id}/resolve
"""

import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_db
from backend.database.repositories import get_user_sessions, get_session_messages
from backend.routers.auth import get_current_user, MOCK_USERS, bearer_scheme
from fastapi.security import HTTPAuthorizationCredentials

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])

# --- In-memory session store ---
SESSIONS: Dict[str, Dict[str, Any]] = {}


# --- WebSocket Manager reference (set by main.py) ---
class _WSManagerRef:
    manager = None

ws_ref = _WSManagerRef()


def set_ws_manager(manager):
    """Called by main.py to inject the WebSocket manager."""
    ws_ref.manager = manager


# --- Pydantic Models ---

class ResolveInput(BaseModel):
    save_to_knowledge: bool = False
    tags: Optional[List[str]] = None

class ApproveInput(BaseModel):
    action: str  # "approve" or "clarify"
    clarification: Optional[str] = None  # Additional text if action is "clarify"


# --- Endpoints ---

@router.post("/create")
async def create_session(
    matricule: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Create a new chat session for a user."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    user = MOCK_USERS.get(matricule, {})
    SESSIONS[session_id] = {
        "id": session_id,
        "user_matricule": matricule,
        "user_token": credentials.credentials,
        "user_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
        "user_role": user.get("role", "Unknown"),
        "status": "active",
        "history": [],
        "created_at": datetime.now().isoformat(),
        "agent_matricule": None,
        "user_ws": None,
        "agent_ws": None,
        "reason": None,
        "trigger_message": None,  # The low-confidence AI response that triggered escalation
        "last_ai_confidence": None,
    }
    logger.info(f"Session created: {session_id} for {matricule}")

    # Persist to PostgreSQL (fire-and-forget)
    asyncio.create_task(_persist_session_create(session_id, matricule))

    # Notify agent dashboard in real time
    if ws_ref.manager:
        await ws_ref.manager.broadcast({
            "type": "NEW_SESSION",
            "payload": {
                "session_id": session_id,
                "user_matricule": matricule,
                "user_name": SESSIONS[session_id]["user_name"],
                "user_role": SESSIONS[session_id]["user_role"],
                "status": "active",
                "created_at": SESSIONS[session_id]["created_at"],
            }
        })

    return {"session_id": session_id}


@router.get("/active")
async def get_active_sessions(matricule: str = Depends(get_current_user)):
    """List all active/pending sessions for the agent queue."""
    active = []
    for sid, s in SESSIONS.items():
        if s["status"] in ("active", "handoff_pending", "agent_connected"):
            active.append({
                "id": s["id"],
                "user_matricule": s["user_matricule"],
                "user_name": s["user_name"],
                "user_role": s["user_role"],
                "status": s["status"],
                "created_at": s["created_at"],
                "reason": s["reason"],
                "message_count": len(s["history"]),
                "last_message": s["history"][-1]["content"][:80] if s["history"] else "",
                "agent_matricule": s["agent_matricule"],
                "last_ai_confidence": s.get("last_ai_confidence"),
            })
    priority = {"handoff_pending": 0, "active": 1, "agent_connected": 2}
    active.sort(key=lambda x: (priority.get(x["status"], 9), x["created_at"]))
    return active


@router.get("/user-chats")
async def get_user_chats(
    matricule: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all chats for the current user (multi-chat support).
    
    Auto-cleans empty sessions older than 5 minutes to prevent ghost chats
    from accumulating when users refresh the page.
    """
    now = datetime.now()
    empty_session_ttl_seconds = 300  # 5 minutes

    # ── Database Hydration ──
    # Hydrate SESSIONS from the PostgreSQL DB in case this container just restarted.
    try:
        db_sessions = await get_user_sessions(db, matricule)
        for db_sess in db_sessions:
            sid = str(db_sess.id)
            if sid not in SESSIONS:
                # Load messages
                db_msgs = await get_session_messages(db, sid)
                history = []
                for m in db_msgs:
                    history.append({
                        "role": m.role.value if hasattr(m.role, 'value') else m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else now.isoformat(),
                        "confidence": m.confidence,
                        "source": m.model_used,
                    })
                user = MOCK_USERS.get(matricule, {})
                
                # Check status
                status_val = db_sess.status.value if hasattr(db_sess.status, 'value') else db_sess.status
                
                SESSIONS[sid] = {
                    "id": sid,
                    "user_matricule": matricule,
                    "user_token": "", # Resurrected sessions don't retain old JWT payload
                    "user_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
                    "user_role": user.get("role", "Unknown"),
                    "status": status_val,
                    "history": history,
                    "created_at": db_sess.created_at.isoformat() if db_sess.created_at else now.isoformat(),
                    "agent_matricule": db_sess.agent_matricule,
                    "user_ws": None,
                    "agent_ws": None,
                    "reason": db_sess.reason,
                }
    except Exception as e:
        logger.error(f"Failed to hydrate sessions from DB: {e}")

    # Cleanup pass: remove this user's empty stale sessions
    stale_ids = []
    for sid, s in SESSIONS.items():
        if s["user_matricule"] != matricule:
            continue
        if len(s["history"]) == 0 and s["status"] == "active":
            try:
                created = datetime.fromisoformat(s["created_at"])
                age_seconds = (now - created).total_seconds()
                if age_seconds > empty_session_ttl_seconds:
                    stale_ids.append(sid)
            except Exception:
                pass

    for sid in stale_ids:
        del SESSIONS[sid]
        logger.debug(f"🧹 Cleaned up empty stale session: {sid}")

    # Build response
    chats = []
    for sid, s in SESSIONS.items():
        if s["user_matricule"] == matricule:
            last_msg = ""
            if s["history"]:
                last_msg = s["history"][-1]["content"][:80]
            chats.append({
                "id": s["id"],
                "status": s["status"],
                "created_at": s["created_at"],
                "message_count": len(s["history"]),
                "last_message": last_msg,
                "reason": s["reason"],
                "has_agent": s["agent_matricule"] is not None,
            })
    # Most recent first
    chats.sort(key=lambda x: x["created_at"], reverse=True)
    return chats


@router.get("/{session_id}/history")
async def get_session_history(session_id: str, matricule: str = Depends(get_current_user)):
    """Get full chat history for a session."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session["status"],
        "user_name": session["user_name"],
        "user_role": session["user_role"],
        "user_matricule": session["user_matricule"],
        "created_at": session["created_at"],
        "agent_matricule": session["agent_matricule"],
        "reason": session["reason"],
        "history": session["history"],
    }


@router.get("/{session_id}/briefing")
async def get_session_briefing(session_id: str, matricule: str = Depends(get_current_user)):
    """
    Agent briefing panel — generates an LLM summary of the conversation 
    and returns structured context so the agent can get up to speed fast.
    """
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history = session["history"]
    user_messages = [m for m in history if m["role"] == "user"]
    ai_messages = [m for m in history if m["role"] == "assistant"]

    # Extract key topics from user messages
    all_user_text = " ".join(m["content"] for m in user_messages)
    topics = _extract_topics(all_user_text)

    # Calculate duration
    try:
        created = datetime.fromisoformat(session["created_at"])
        duration_minutes = int((datetime.now() - created).total_seconds() / 60)
    except Exception:
        duration_minutes = 0

    # Find the last AI confidence before escalation
    last_confidence = session.get("last_ai_confidence")
    if last_confidence is None:
        for msg in reversed(history):
            if msg.get("confidence"):
                last_confidence = msg["confidence"]
                break

    # Build conversation excerpt for LLM summary
    conversation_excerpt = _build_conversation_excerpt(history, max_messages=10)

    # Generate LLM summary (async)
    ai_summary = await _generate_briefing_summary(
        session["user_name"],
        session["user_role"],
        session["reason"],
        conversation_excerpt,
    )

    return {
        "session_id": session_id,
        "client": {
            "name": session["user_name"],
            "role": session["user_role"],
            "matricule": session["user_matricule"],
        },
        "escalation_reason": session["reason"],
        "ai_summary": ai_summary,
        "topics": topics,
        "duration_minutes": duration_minutes,
        "message_count": len(history),
        "user_message_count": len(user_messages),
        "ai_message_count": len(ai_messages),
        "last_ai_confidence": last_confidence,
        "trigger_message": session.get("trigger_message"),
        "status": session["status"],
    }


@router.post("/{session_id}/approve")
async def approve_ai_response(
    session_id: str,
    body: ApproveInput,
    matricule: str = Depends(get_current_user),
):
    """
    Agent approves or clarifies the AI's trigger response.
    
    - approve: The AI's response was good enough, send it to the user as-is
    - clarify: Agent adds clarification, combined with original AI response
    """
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    trigger = session.get("trigger_message")
    if not trigger:
        raise HTTPException(status_code=400, detail="No trigger message to approve")

    user = MOCK_USERS.get(matricule, {})
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()

    if body.action == "approve":
        # Send the AI's original response to the user as agent-approved
        approved_msg = {
            "role": "agent",
            "content": f"✅ {trigger['content']}",
            "timestamp": datetime.now().isoformat(),
            "approved_from_ai": True,
        }
        session["history"].append(approved_msg)
        # Notify user via WebSocket
        user_ws = session.get("user_ws")
        if user_ws:
            try:
                await user_ws.send_json({
                    "type": "agent_message",
                    "content": approved_msg["content"],
                    "timestamp": approved_msg["timestamp"],
                    "approved_from_ai": True,
                })
            except Exception:
                pass
        return {"status": "approved", "message": "AI response approved and sent to user"}

    elif body.action == "clarify":
        # Agent augments the AI response with clarification
        clarified_content = trigger["content"]
        if body.clarification:
            clarified_content += f"\n\n📝 Précision de l'agent {agent_name} : {body.clarification}"
        
        clarified_msg = {
            "role": "agent",
            "content": clarified_content,
            "timestamp": datetime.now().isoformat(),
            "clarified_from_ai": True,
        }
        session["history"].append(clarified_msg)
        user_ws = session.get("user_ws")
        if user_ws:
            try:
                await user_ws.send_json({
                    "type": "agent_message",
                    "content": clarified_msg["content"],
                    "timestamp": clarified_msg["timestamp"],
                    "clarified_from_ai": True,
                })
            except Exception:
                pass
        return {"status": "clarified", "message": "Clarified response sent to user"}

    raise HTTPException(status_code=400, detail="action must be 'approve' or 'clarify'")


@router.post("/{session_id}/takeover")
async def takeover_session(session_id: str, matricule: str = Depends(get_current_user)):
    """Agent takes over a session."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    user = MOCK_USERS.get(matricule, {})
    session["status"] = "agent_connected"
    session["agent_matricule"] = matricule
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()
    session["history"].append({
        "role": "system",
        "content": f"L'agent {agent_name} vient de rejoindre. Il a lu le résumé de votre conversation.",
        "timestamp": datetime.now().isoformat()
    })
    # Notify user
    user_ws = session.get("user_ws")
    if user_ws:
        try:
            await user_ws.send_json({
                "type": "agent_joined",
                "agent_name": agent_name,
                "message": f"L'agent {agent_name} vient de rejoindre. Il a lu le résumé de votre conversation.",
            })
        except Exception:
            pass
    # Broadcast
    if ws_ref.manager:
        await ws_ref.manager.broadcast({"type": "AGENT_JOINED", "payload": {"session_id": session_id, "agent": agent_name}})
    logger.info(f"Agent {matricule} took over session {session_id}")

    # Persist status change (fire-and-forget)
    asyncio.create_task(_persist_session_status(session_id, "agent_connected", matricule))

    return {"status": "taken_over", "session_id": session_id}


@router.post("/{session_id}/resolve")
async def resolve_session(
    session_id: str,
    body: Optional[ResolveInput] = None,
    matricule: str = Depends(get_current_user),
):
    """Mark a session as resolved, optionally saving to HITL knowledge base."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["status"] = "resolved"
    session["history"].append({
        "role": "system",
        "content": "Session résolue par l'agent.",
        "timestamp": datetime.now().isoformat()
    })

    # --- HITL Feedback Loop ---
    hitl_result = None
    if body and body.save_to_knowledge:
        user_questions = [m for m in session["history"] if m["role"] == "user"]
        agent_answers = [m for m in session["history"] if m["role"] == "agent"]

        if user_questions and agent_answers:
            question = user_questions[-1]["content"]
            answer = agent_answers[-1]["content"]
            user = MOCK_USERS.get(matricule, {})
            agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()

            from backend.services.rag_service import async_add_hitl_knowledge
            hitl_result = await async_add_hitl_knowledge(
                session_id=session_id,
                question=question,
                answer=answer,
                agent_matricule=matricule,
                agent_name=agent_name,
                tags=body.tags,
            )
            logger.info(f"🧠 HITL knowledge saved from session {session_id}")

    # Notify user
    user_ws = session.get("user_ws")
    if user_ws:
        try:
            await user_ws.send_json({"type": "session_resolved"})
        except Exception:
            pass

    if ws_ref.manager:
        await ws_ref.manager.broadcast({"type": "SESSION_RESOLVED", "payload": {"session_id": session_id}})

    logger.info(f"Session {session_id} resolved by {matricule}")

    # Persist resolution (fire-and-forget)
    asyncio.create_task(_persist_session_status(session_id, "resolved"))

    result = {"status": "resolved"}
    if hitl_result:
        result["hitl_knowledge"] = hitl_result
    return result


# ==============================================================
# HELPER FUNCTIONS
# ==============================================================

def _extract_topics(text: str) -> list:
    """Extract key topics/keywords from user messages."""
    # Insurance-domain keyword extraction
    topic_keywords = {
        "remboursement": "Remboursement",
        "rembourse": "Remboursement",
        "dentaire": "Soins dentaires",
        "dent": "Soins dentaires",
        "optique": "Optique",
        "lunette": "Optique",
        "hospitalisation": "Hospitalisation",
        "hopital": "Hospitalisation",
        "urgence": "Urgences",
        "maternite": "Maternité",
        "naissance": "Maternité",
        "grossesse": "Maternité",
        "beneficiaire": "Bénéficiaires",
        "enfant": "Bénéficiaires",
        "conjoint": "Bénéficiaires",
        "carte": "Carte adhérent",
        "adherent": "Adhésion",
        "cotisation": "Cotisations",
        "prime": "Primes",
        "reclamation": "Réclamation",
        "plainte": "Réclamation",
        "medicament": "Pharmacie",
        "pharmacie": "Pharmacie",
        "consultation": "Consultation",
        "medecin": "Consultation",
        "kine": "Kinésithérapie",
        "labo": "Analyses",
        "analyse": "Analyses",
        "radio": "Imagerie",
        "irm": "Imagerie",
        "scanner": "Imagerie",
        "vaccin": "Vaccination",
        "dossier": "Dossiers",
        "prestation": "Prestations",
        "facture": "Facturation",
    }
    text_lower = text.lower()
    found = set()
    for keyword, topic in topic_keywords.items():
        if keyword in text_lower:
            found.add(topic)
    return list(found)[:6]  # Max 6 topics


def _build_conversation_excerpt(history: list, max_messages: int = 10) -> str:
    """Build a text excerpt of the conversation for LLM summarization."""
    recent = history[-max_messages:] if len(history) > max_messages else history
    lines = []
    for msg in recent:
        role_label = {
            "user": "Client",
            "assistant": "IA",
            "agent": "Agent",
            "system": "Système"
        }.get(msg["role"], msg["role"])
        lines.append(f"{role_label}: {msg['content']}")
    return "\n".join(lines)


async def _generate_briefing_summary(
    user_name: str,
    user_role: str,
    reason: str,
    conversation_excerpt: str,
) -> str:
    """Generate an LLM summary of the conversation for the agent briefing."""
    try:
        from backend.config import get_settings
        settings = get_settings()
        
        # Use the same LLM patterns as agent.py to avoid import/config mismatches
        if settings.USE_LOCAL_LLM:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                base_url=settings.OLLAMA_BASE_URL,
                api_key="ollama",
                model=settings.OLLAMA_MODEL,
                temperature=0.1,
            )
        else:
            from langchain_google_vertexai import ChatVertexAI
            llm = ChatVertexAI(
                model="gemini-2.5-flash",
                project=settings.GCP_PROJECT_ID,
                location=settings.GCP_LOCATION,
                temperature=0.1,
            )

        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"""Tu es un assistant interne pour les agents du support I-Santé.
Génère un résumé concis (3-4 phrases) de cette conversation pour aider l'agent à comprendre rapidement la situation.

Client: {user_name} ({user_role})
Raison d'escalade: {reason or 'Non spécifiée'}

Conversation:
{conversation_excerpt[:3000]}

Résumé pour l'agent (en français, 3-4 phrases max):"""

        import asyncio
        response = await asyncio.wait_for(
            llm.ainvoke([
                SystemMessage(content="Tu résumes des conversations client pour les agents de support."),
                HumanMessage(content=prompt),
            ]),
            timeout=15.0,
        )
        return response.content.strip()

    except Exception as e:
        logger.warning(f"⚠️ Briefing summary generation failed: {e}")
        # Fallback: simple extractive summary
        return _fallback_summary(user_name, user_role, reason, conversation_excerpt)


def _fallback_summary(user_name: str, user_role: str, reason: str, excerpt: str) -> str:
    """Simple extractive summary when LLM is unavailable."""
    lines = excerpt.split("\n")
    client_lines = [l for l in lines if l.startswith("Client:")]
    if client_lines:
        first_q = client_lines[0].replace("Client: ", "")
        summary = f"{user_name} ({user_role}) a contacté le support. "
        summary += f"Question initiale : \"{first_q[:100]}\". "
        if reason:
            summary += f"Escaladé car : {reason}."
        return summary
    return f"{user_name} ({user_role}) a contacté le support. Raison: {reason or 'non spécifiée'}."


# ==============================================================
# PERSISTENCE HELPERS (fire-and-forget dual-write to PostgreSQL)
# ==============================================================

async def _persist_session_create(session_id: str, user_matricule: str):
    """Persist a new session to PostgreSQL. Silently fails if DB is unavailable."""
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import create_session as db_create

        async with async_session_factory() as db:
            await db_create(db, session_id, user_matricule)
            await db.commit()
    except Exception as e:
        logger.debug(f"Session DB persist skipped: {e}")


async def _persist_session_status(
    session_id: str,
    status: str,
    agent_matricule: str = None,
):
    """Persist session status change to PostgreSQL. Silently fails if DB is unavailable."""
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import update_session_status

        async with async_session_factory() as db:
            await update_session_status(
                db, session_id, status,
                agent_matricule=agent_matricule,
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"Session status DB persist skipped: {e}")
