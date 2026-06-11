"""
Escalation Flow — the handoff banner contract, in one place.

Every escalation path (graph escalation, low-confidence, service-degraded,
manual request) emits the same `handoff_started` event through here, so the
queue_position / estimated_wait_min fields can never be forgotten on one path.
"""

import logging

from backend.services.session_store import queue_position

logger = logging.getLogger("I-Way-Twin")

# Rough per-case handling estimate used for the banner's wait hint.
_MINUTES_PER_CASE = 3


async def send_handoff_started(websocket, session_id: str, reason: str, *, degraded: bool = False):
    """Emit the handoff_started banner event with the real queue position."""
    pos = queue_position(session_id)
    payload = {
        "type": "handoff_started",
        "reason": reason,
        "keep_chatting": True,
        "queue_position": pos,
        "estimated_wait_min": pos * _MINUTES_PER_CASE,
    }
    if degraded:
        payload["degraded"] = True
    await websocket.send_json(payload)
