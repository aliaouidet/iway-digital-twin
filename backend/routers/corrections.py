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

from backend.routers.auth import get_current_user, require_role, MOCK_USERS

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/corrections", tags=["Corrections"])


# --- In-memory corrections store ---
CORRECTIONS: List[dict] = []


# --- Pydantic ---

class CorrectionInput(BaseModel):
    session_id: str
    wrong_message_content: str
    correct_answer: str
    correction_type: str = "factual_error"  # factual_error | outdated | hallucination | incomplete


@router.post("")
async def flag_ai_correction(data: CorrectionInput, matricule: str = Depends(require_role("Agent", "Admin"))):
    """
    Agent flags an incorrect AI response.
    This creates a correction record and fires an admin alert.
    The incorrect answer is NEVER added to the knowledge base.
    """
    user = MOCK_USERS.get(matricule, {})
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

    logger.warning(
        f"⚠️ AI CORRECTION flagged by {agent_name}: "
        f"type={data.correction_type}, session={data.session_id}"
    )

    return {
        "status": "flagged",
        "correction_id": correction["id"],
        "message": "AI response flagged as incorrect. It will NOT be added to the knowledge base.",
    }


@router.get("")
async def list_corrections(matricule: str = Depends(require_role("Agent", "Admin"))):
    """List all AI corrections for admin review."""
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
