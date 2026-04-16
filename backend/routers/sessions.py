"""
Sessions Router — HITL session lifecycle management.

Routes:
  POST /api/v1/sessions/create
  GET  /api/v1/sessions/active
  GET  /api/v1/sessions/{session_id}/history
  POST /api/v1/sessions/{session_id}/takeover
  POST /api/v1/sessions/{session_id}/resolve
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.routers.auth import get_current_user, MOCK_USERS

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])

# --- In-memory session store (will migrate to PostgreSQL in Phase 2 completion) ---
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


# --- Endpoints ---

@router.post("/create")
async def create_session(matricule: str = Depends(get_current_user)):
    """Create a new chat session for a user."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    user = MOCK_USERS.get(matricule, {})
    SESSIONS[session_id] = {
        "id": session_id,
        "user_matricule": matricule,
        "user_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
        "user_role": user.get("role", "Unknown"),
        "status": "active",
        "history": [],
        "created_at": datetime.now().isoformat(),
        "agent_matricule": None,
        "user_ws": None,
        "agent_ws": None,
        "reason": None,
    }
    logger.info(f"Session created: {session_id} for {matricule}")
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
            })
    priority = {"handoff_pending": 0, "active": 1, "agent_connected": 2}
    active.sort(key=lambda x: (priority.get(x["status"], 9), x["created_at"]))
    return active


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
        "content": f"Agent {agent_name} a rejoint la conversation.",
        "timestamp": datetime.now().isoformat()
    })
    # Notify user
    user_ws = session.get("user_ws")
    if user_ws:
        try:
            await user_ws.send_json({"type": "agent_joined", "agent_name": agent_name})
        except Exception:
            pass
    # Broadcast
    if ws_ref.manager:
        await ws_ref.manager.broadcast({"type": "AGENT_JOINED", "payload": {"session_id": session_id, "agent": agent_name}})
    logger.info(f"Agent {matricule} took over session {session_id}")
    return {"status": "taken_over", "session_id": session_id}


@router.post("/{session_id}/resolve")
async def resolve_session(
    session_id: str,
    body: Optional[ResolveInput] = None,
    matricule: str = Depends(get_current_user),
):
    """
    Mark a session as resolved.
    
    If body.save_to_knowledge is True, the agent's last answer and the user's
    question are embedded and added to the HITL-validated knowledge base.
    These entries receive a 15% trust boost in future RAG searches.
    """
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["status"] = "resolved"
    session["history"].append({
        "role": "system",
        "content": "Session resolue par l'agent.",
        "timestamp": datetime.now().isoformat()
    })

    # --- HITL Feedback Loop ---
    hitl_result = None
    if body and body.save_to_knowledge:
        # Extract the last user question and last agent answer
        user_questions = [m for m in session["history"] if m["role"] == "user"]
        agent_answers = [m for m in session["history"] if m["role"] == "agent"]

        if user_questions and agent_answers:
            question = user_questions[-1]["content"]
            answer = agent_answers[-1]["content"]
            user = MOCK_USERS.get(matricule, {})
            agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()

            from backend.services.rag_service import add_hitl_knowledge
            hitl_result = add_hitl_knowledge(
                session_id=session_id,
                question=question,
                answer=answer,
                agent_matricule=matricule,
                agent_name=agent_name,
                tags=body.tags,
            )
            logger.info(f"🧠 HITL knowledge saved from session {session_id}")
        else:
            logger.warning(f"Cannot save HITL knowledge: no Q&A pairs in session {session_id}")

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

    result = {"status": "resolved"}
    if hitl_result:
        result["hitl_knowledge"] = hitl_result
    return result
