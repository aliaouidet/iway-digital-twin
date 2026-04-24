"""
Routing Functions — Conditional edges for the Claims StateGraph.

All 4 routing functions that determine which node to execute next:
  - pre_intake_router:  START → intake or stall
  - route_by_intent:    intake → rag/extraction/escalation/action_router
  - route_action:       action_router → dossier_lookup or beneficiary_lookup
  - route_by_confidence: draft_response → respond/clarification/handoff
"""

import logging
from typing import Literal

from state import ClaimsGraphState, ClaimIntent

logger = logging.getLogger("I-Way-Twin")


def pre_intake_router(
    state: ClaimsGraphState,
) -> Literal["intake", "stall"]:
    """
    Pre-Intake Router (after START).

    If the claim is currently pending human review, intercept the
    user's message and route to the stall_node.
    """
    claim_status = state.get("claim_status", "active")

    if claim_status == "pending_human":
        logger.info("Pre-intake: claim_status=pending_human -> stall")
        return "stall"
    else:
        return "intake"


def route_by_intent(
    state: ClaimsGraphState,
) -> Literal["rag_retrieval", "claim_extraction", "escalation", "action_router"]:
    """
    Conditional edge after intake_node (4-way branch).

    Routes the claim to the appropriate processing path based on
    the classified intent.
    """
    intent = state.get("intent")

    if intent == ClaimIntent.ESCALATION:
        return "escalation"
    elif intent == ClaimIntent.CLAIM_ACTION:
        return "claim_extraction"
    elif intent == ClaimIntent.PERSONAL_LOOKUP:
        return "action_router"
    else:
        # INFO_QUERY goes through RAG
        return "rag_retrieval"


def route_action(
    state: ClaimsGraphState,
) -> Literal["dossier_lookup", "beneficiary_lookup"]:
    """
    Conditional edge after action_router_node.

    Uses keyword-based routing as a deterministic fallback
    after LLM classification.
    """
    msg = state["messages"][-1].content.lower()

    beneficiary_keywords = [
        "beneficiaire", "famille", "conjoint", "enfant",
        "couvert", "ayant", "contrat", "dependant",
    ]

    if any(kw in msg for kw in beneficiary_keywords):
        logger.info("Action route -> beneficiary_lookup")
        return "beneficiary_lookup"
    else:
        logger.info("Action route -> dossier_lookup")
        return "dossier_lookup"


def route_by_confidence(
    state: ClaimsGraphState,
) -> Literal["respond", "clarification", "handoff"]:
    """
    3-way conditional edge after draft_response_node.

    Decision tree:
      1. confidence >= 0.70  →  respond directly (auto-respond)
      2. confidence < 0.70 AND claim_details has missing required fields
                              →  clarification (ask user for the gaps)
      3. confidence < 0.70 AND claim_details is complete
                              →  handoff (async transfer to human supervisor)
    """
    CONFIDENCE_THRESHOLD = 0.70
    confidence = state.get("confidence", 0.0) or 0.0

    if confidence >= CONFIDENCE_THRESHOLD:
        logger.info(f"Confidence {confidence:.2f} >= {CONFIDENCE_THRESHOLD} -> auto-respond")
        return "respond"

    # Low confidence — check if we're missing claim data
    claim_details = state.get("claim_details")

    if claim_details is not None:
        missing = claim_details.missing_required_fields()
        if missing:
            logger.info(
                f"Confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD}, "
                f"missing fields: {missing} -> clarification"
            )
            return "clarification"

    # Low confidence + complete details (or info_query with no details) → handoff
    logger.info(
        f"Confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD}, "
        f"details complete -> handoff"
    )
    return "handoff"
