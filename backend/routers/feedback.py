"""
Feedback Router — CSAT feedback collection and aggregation.

Extracted from main.py to follow Clean Architecture routing patterns.
"""

import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(tags=["Sessions"])

# In-memory feedback store
_feedback_store: list[dict] = []


@router.post("/api/v1/sessions/{session_id}/feedback")
async def submit_feedback(session_id: str, body: dict):
    """
    Submit CSAT feedback after session resolved.
    Body: { rating: 'positive' | 'negative', comment?: string }
    """
    from backend.routers.sessions import SESSIONS

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


@router.get("/api/v1/feedback/stats", tags=["Monitoring"])
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
