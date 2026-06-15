"""
Corrections Router — AI error flagging by agents.

Routes:
  POST /api/v1/corrections         — Flag an incorrect AI response
  GET  /api/v1/corrections         — List all corrections (admin view)
"""

import uuid
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.routers.auth import get_current_user, require_role, resolve_user
from backend.database.connection import get_db
from backend.database.repositories import save_correction

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/corrections", tags=["Corrections"])


# --- In-memory corrections cache (DB is the source of truth; this survives a
#     DB outage and serves the admin list without a round-trip). ---
CORRECTIONS: List[dict] = []


def _resolve_user_question(session_id: str, wrong_answer: str) -> str | None:
    """Find the USER question that triggered a wrong AI answer.

    The correction must be retrievable by what a *future user* would ask — i.e.
    the user's question, not the AI's wrong reply. Walk the live session history
    back from the flagged assistant message to the nearest preceding user turn.
    """
    from backend.routers.sessions import SESSIONS
    history = (SESSIONS.get(session_id) or {}).get("history", [])
    wrong = (wrong_answer or "").strip()
    idx = next((i for i, m in enumerate(history)
                if (m.get("content") or "").strip() == wrong), None)
    if idx is not None:
        for j in range(idx - 1, -1, -1):
            if history[j].get("role") == "user":
                return history[j].get("content")
    for m in reversed(history):  # fallback: last user message in the thread
        if m.get("role") == "user":
            return m.get("content")
    return None


# --- Pydantic ---

class CorrectionInput(BaseModel):
    session_id: str
    wrong_message_content: str
    correct_answer: str
    correction_type: str = "factual_error"  # factual_error | outdated | hallucination | incomplete


@router.post("")
async def flag_ai_correction(
    data: CorrectionInput,
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """
    Agent flags an incorrect AI response.
    This creates a correction record and fires an admin alert.
    The incorrect answer is NEVER added to the knowledge base.
    """
    user = await resolve_user(matricule) or {}
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()

    correction = {
        "id": f"cor-{uuid.uuid4().hex[:8]}",
        "session_id": data.session_id,
        "wrong_message_content": data.wrong_message_content,
        "correct_answer": data.correct_answer,
        "correction_type": data.correction_type,
        "agent_matricule": matricule,
        "agent_name": agent_name,
        "created_at": datetime.now().isoformat(),
    }

    CORRECTIONS.append(correction)

    # Persist to the AICorrection table (durable; survives restart, feeds the
    # admin curation view). Best-effort — a FK/UUID miss must not block the flow.
    try:
        await save_correction(
            db,
            session_id=data.session_id,
            correct_answer=data.correct_answer,
            agent_matricule=matricule,
            correction_type=data.correction_type,
        )
    except Exception as e:
        logger.warning(f"[HITL] Correction DB persist failed (kept in-memory): {e}")

    logger.warning(
        f"⚠️ AI CORRECTION flagged by {agent_name}: "
        f"type={data.correction_type}, session={data.session_id}"
    )

    # --- Dispatch Celery task: re-embed the corrected Q&A into RAG ---
    # Embed the USER's question (not the AI's wrong reply) as the retrieval key.
    user_question = _resolve_user_question(data.session_id, data.wrong_message_content) \
        or data.wrong_message_content
    try:
        from backend.workers.hitl_worker import embed_hitl_feedback
        embed_hitl_feedback.delay(
            session_id=data.session_id,
            question=user_question,
            corrected_answer=data.correct_answer,
            agent_matricule=matricule,
            agent_name=agent_name,
            corrected_from=data.wrong_message_content,
        )
        logger.info(f"[HITL] 📨 Celery task dispatched for correction {correction['id']}")
    except Exception as e:
        logger.warning(f"[HITL] Celery dispatch failed (non-critical): {e}")

    return {
        "status": "flagged",
        "correction_id": correction["id"],
        "message": "AI response flagged. Corrected answer is being re-embedded into the knowledge base.",
    }


@router.get("")
async def list_corrections(
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """List all AI corrections for admin review — durable (DB) with in-memory fallback."""
    try:
        from backend.database.repositories import get_all_corrections
        rows = await get_all_corrections(db)
        if rows:
            corrections = [{
                "id": str(c.id),
                "session_id": str(c.session_id),
                "correct_answer": c.correct_answer,
                "correction_type": c.correction_type.value if hasattr(c.correction_type, "value") else c.correction_type,
                "agent_matricule": c.agent_matricule,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            } for c in rows]
            by_type = {}
            for c in corrections:
                by_type[c["correction_type"]] = by_type.get(c["correction_type"], 0) + 1
            return {"corrections": corrections, "total": len(corrections), "by_type": by_type}
    except Exception as e:
        logger.debug(f"Corrections DB read failed, using in-memory: {e}")

    return {
        "corrections": CORRECTIONS,
        "total": len(CORRECTIONS),
        "by_type": _count_by_type(),
    }


def _count_by_type():
    counts = {}
    for c in CORRECTIONS:
        t = c["correction_type"]
        counts[t] = counts.get(t, 0) + 1
    return counts
