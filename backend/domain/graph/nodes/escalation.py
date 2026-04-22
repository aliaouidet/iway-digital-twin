"""
Node 7: Escalation — Immediate ticket creation.

Triggered when the user explicitly demands a human agent or is
detected as angry/frustrated.
"""

import logging

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


async def escalation_node(state: ClaimsGraphState) -> dict:
    """
    Node 2c: Escalation Handler.

    Unlike handoff_node, this is an immediate, explicit escalation.

    TODO (Phase 4): Wire to iway_client.escalate_to_support() and
    broadcast NEW_ESCALATION via WebSocket manager.
    """
    reason = state["messages"][-1].content

    logger.info(f"Escalation triggered: {reason[:60]}...")

    return {
        "escalation_ticket": {
            "case_id": "ESC-STUB-001",
            "queue_position": 1,
            "estimated_wait": "5 minutes",
        },
        "escalation_reason": reason,
        "claim_status": "pending_human",
        "final_response": (
            "Je comprends votre frustration. Un agent humain va prendre "
            "en charge votre conversation dans les plus brefs delais. "
            "Votre position dans la file : 1."
        ),
    }
