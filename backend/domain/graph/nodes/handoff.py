"""
Node 4b: Handoff — Async transfer to human supervisor.

Triggered when draft has low confidence but claim details are complete,
indicating a genuinely complex case that needs human review.
"""

import logging

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


async def handoff_node(state: ClaimsGraphState) -> dict:
    """
    Node 4b: Asynchronous Human Handoff.

    Sets claim_status = "pending_human" so future messages get stalled.
    The graph does NOT freeze — the user can continue chatting via stall_node.
    """
    draft = state.get("draft_response", "")
    confidence = state.get("confidence", 0.0)
    claim_details = state.get("claim_details")

    logger.info(
        f"Handoff triggered -- confidence: {confidence:.2f}, "
        f"claim_details: {claim_details}"
    )

    handoff_message = (
        "Votre dossier necessite une verification par un superviseur. "
        "J'ai transmis toutes les informations que vous m'avez fournies. "
        "Le traitement prend generalement quelques minutes. "
        "En attendant, je reste disponible si vous avez d'autres questions !"
    )

    return {
        "final_response": handoff_message,
        "claim_status": "pending_human",
    }
