"""
Session Store — single owner of the in-process session state.

This module is the ONE place that holds the live session map. Routers
(`routers/sessions.py` re-exports `SESSIONS` for backward compatibility) and
the chat pipeline all share this dict, which fixes the previous inverted
dependency where services imported state from a router module.

It also owns:
  - queue_position():       real handoff-queue position (used by the banner)
  - hydrate_all_sessions(): startup restore of ALL non-resolved sessions from
    PostgreSQL, so the agent escalation queue survives API restarts.
    (Previously hydration only happened lazily per-user on /user-chats —
    after a restart, handoff_pending users were invisible to agents until
    they happened to send another message.)
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("I-Way-Twin")

# The authoritative in-process session map.
SESSIONS: Dict[str, Dict[str, Any]] = {}


def queue_position(session_id: str) -> int:
    """1-based position in the human-handoff queue (this session counted last).

    Truthful replacement for the old hardcoded 'position : 1' — counts how many
    OTHER sessions are already awaiting an agent.
    """
    ahead = sum(
        1 for sid, s in SESSIONS.items()
        if sid != session_id and s.get("status") == "handoff_pending"
    )
    return ahead + 1


async def hydrate_all_sessions() -> int:
    """Restore all non-resolved sessions (with histories) from PostgreSQL.

    Called once from the FastAPI lifespan. Best-effort: a DB outage degrades to
    an empty store (same as before), never blocks startup.
    """
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import get_active_sessions, get_session_messages
        from backend.routers.auth import resolve_user
    except Exception as e:  # pragma: no cover — import-time env issues
        logger.warning(f"⚠️ Session hydration unavailable: {e}")
        return 0

    restored = 0
    try:
        async with async_session_factory() as db:
            db_sessions = await get_active_sessions(db)
            for db_sess in db_sessions:
                sid = str(db_sess.id)
                if sid in SESSIONS:
                    continue

                db_msgs = await get_session_messages(db, sid)
                history = []
                for m in db_msgs:
                    history.append({
                        "role": m.role.value if hasattr(m.role, "value") else m.role,
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                        "confidence": m.confidence,
                        "source": m.model_used,
                    })

                matricule = db_sess.user_matricule
                user = await resolve_user(matricule) or {}
                status_val = db_sess.status.value if hasattr(db_sess.status, "value") else db_sess.status

                SESSIONS[sid] = {
                    "id": sid,
                    "user_matricule": matricule,
                    "user_token": "",  # credentials are never persisted/restored
                    "user_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip() or matricule,
                    "user_role": user.get("role", "Unknown"),
                    "user_num_police": user.get("num_police", ""),
                    "user_id_tiers": user.get("id_tiers", ""),
                    "status": status_val,
                    "history": history,
                    "created_at": db_sess.created_at.isoformat() if db_sess.created_at else None,
                    "agent_matricule": db_sess.agent_matricule,
                    "user_ws": None,
                    "agent_ws": None,
                    "reason": db_sess.reason,
                    "trigger_message": None,
                    "last_ai_confidence": None,
                }
                restored += 1
    except Exception as e:
        logger.warning(f"⚠️ Session hydration failed (non-critical): {e}")
        return restored

    if restored:
        pending = sum(1 for s in SESSIONS.values() if s["status"] == "handoff_pending")
        logger.info(f"💾 Hydrated {restored} session(s) from PostgreSQL ({pending} awaiting an agent)")
    return restored
