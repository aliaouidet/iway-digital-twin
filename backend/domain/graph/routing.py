"""
Routing Functions — Conditional edges for the Claims StateGraph.

All 4 routing functions that determine which node to execute next:
  - pre_intake_router:  START → intake or stall
  - route_by_intent:    intake → rag/extraction/escalation/action_router
  - route_action:       action_router → dossier_lookup or beneficiary_lookup
  - route_by_confidence: draft_response → respond/clarification/handoff
"""

import re
import logging
from typing import Literal, Optional

from backend.domain.state import ClaimsGraphState, ClaimIntent

logger = logging.getLogger("I-Way-Twin")


# ── Personal-lookup sub-routing (keyword + dossier-number heuristics) ──
#
# A PERSONAL_LOOKUP intent fans out to one of four handlers. The decision is
# deterministic (no LLM): keyword match + a dossier-number probe. Shared by the
# single-intent `route_action` edge AND the multi-intent executor so both paths
# behave identically.

_RECLAMATION_KEYWORDS = [
    "reclamation", "réclamation", "reclamations", "réclamations",
    "plainte", "contestation", "litige", "reclamer", "réclamer",
]

_BENEFICIARY_KEYWORDS = [
    "beneficiaire", "bénéficiaire", "famille", "conjoint", "enfant",
    "couvert", "ayant", "dependant", "dépendant", "membres",
]

_FACTURE_KEYWORDS = [
    "facture", "factures", "facturation",
]

_PLAFOND_KEYWORDS = [
    "plafond", "plafonds", "consommation", "consommé", "consomme",
    "disponible", "solde restant", "montant restant",
]

# Signals that the user wants ONE specific dossier (→ detail), not the list.
_DETAIL_KEYWORDS = [
    "detail", "détail", "details", "détails", "dossier", "statut", "suivi",
    "ou en est", "où en est", "numero", "numéro", "reference", "référence",
    "etat de", "état de",
]

# Matches a dossier/reference token: "DOS-2026-0042", "BS123456", or a bare 5+ digit id.
# Bare numbers need >= 5 digits so years ("2024") and round amounts ("2000 TND")
# don't masquerade as dossier references.
_DOSSIER_RE = re.compile(r"\b([A-Za-z]{2,}[-\w]*\d{3,}|\d{5,})\b")


def extract_dossier_number(message: str) -> Optional[str]:
    """Pull a dossier/reference number from free text, or None if absent."""
    if not message:
        return None
    m = _DOSSIER_RE.search(message)
    return m.group(1) if m else None


def classify_personal_lookup(
    message: str,
) -> Literal[
    "reclamation_lookup", "facture_lookup", "plafond_lookup",
    "dossier_detail_lookup", "beneficiary_lookup", "dossier_lookup",
]:
    """Pick the personal-lookup handler for a message (deterministic).

    Priority: réclamations → factures → plafonds/consommation →
    specific-dossier detail → bénéficiaires → dossier list.

    Note: GENERAL plafond questions ("quel est le plafond dentaire ?") classify
    as info_query at the intent level and never reach this function — only
    possessive/personal phrasings ("mon plafond restant") land here.
    """
    msg = (message or "").lower()

    if any(kw in msg for kw in _RECLAMATION_KEYWORDS):
        return "reclamation_lookup"

    if any(kw in msg for kw in _FACTURE_KEYWORDS):
        return "facture_lookup"

    if any(kw in msg for kw in _PLAFOND_KEYWORDS):
        return "plafond_lookup"

    # A specific dossier number + a "detail/dossier/statut" cue → single-dossier detail.
    if any(kw in msg for kw in _DETAIL_KEYWORDS) and extract_dossier_number(message):
        return "dossier_detail_lookup"

    if any(kw in msg for kw in _BENEFICIARY_KEYWORDS):
        return "beneficiary_lookup"

    return "dossier_lookup"


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
) -> Literal["rag_retrieval", "claim_extraction", "escalation", "action_router", "provider_search", "draft_response"]:
    """
    Conditional edge after intake_node (6-way branch).

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
    elif intent == ClaimIntent.PROVIDER_SEARCH:
        return "provider_search"
    elif intent == ClaimIntent.SMALL_TALK:
        return "draft_response"
    else:
        # INFO_QUERY goes through RAG
        return "rag_retrieval"


def route_after_decompose(
    state: ClaimsGraphState,
) -> Literal["rag_retrieval", "claim_extraction", "escalation", "action_router", "provider_search", "draft_response", "multi_executor"]:
    """
    Conditional edge after decompose_node (opt-in multi-intent).

    Decision logic:
      - If 1 sub-intent  → fast path (same as route_by_intent, zero overhead)
      - If >1 sub-intents → multi_executor for concurrent tool execution

    This is the primary routing function used by the graph builder.
    route_by_intent is kept for backward compatibility.
    """
    sub_intents = state.get("sub_intents", [])

    if len(sub_intents) > 1:
        # An explicit request for a human OUTRANKS the other sub-intents: the
        # multi-executor cannot run escalation (it would be silently dropped),
        # so route the whole turn down the escalation path instead.
        if any(s.get("intent") == "escalation" for s in sub_intents):
            logger.info("Multi-intent contains escalation -> escalation path dominates")
            return "escalation"
        logger.info(f"Multi-intent detected ({len(sub_intents)} sub-intents) -> multi_executor")
        return "multi_executor"

    # Single intent — use the fast path (no overhead)
    return route_by_intent(state)


def route_action(
    state: ClaimsGraphState,
) -> Literal[
    "dossier_lookup", "beneficiary_lookup", "reclamation_lookup",
    "dossier_detail_lookup", "facture_lookup", "plafond_lookup",
]:
    """
    Conditional edge after action_router_node (6-way branch).

    Deterministic keyword/number routing of a PERSONAL_LOOKUP to the right
    handler: dossier list, single-dossier detail, beneficiaries, réclamations,
    factures, or plafonds/consommation.
    """
    target = classify_personal_lookup(state["messages"][-1].content)
    logger.info(f"Action route -> {target}")
    return target


def route_by_confidence(
    state: ClaimsGraphState,
) -> Literal["respond", "clarification", "handoff", "draft_response"]:
    """
    4-way conditional edge after compliance_check_node.

    Decision tree:
      1. confidence >= 0.70  →  respond directly (auto-respond)
      2. compliance_notes exist AND retry_count < 2
                              →  draft_response (SELF-CORRECTION: retry with error context)
      3. confidence < 0.70 AND claim_details has missing required fields
                              →  clarification (ask user for the gaps)
      4. confidence < 0.70 AND claim_details is complete
                              →  handoff (async transfer to human supervisor)
    """
    CONFIDENCE_THRESHOLD = 0.70
    MAX_RETRIES = 2

    confidence = state.get("confidence", 0.0) or 0.0
    compliance_notes = state.get("compliance_notes") or []
    retry_count = state.get("retry_count", 0) or 0

    if confidence >= CONFIDENCE_THRESHOLD:
        logger.info(f"Confidence {confidence:.2f} >= {CONFIDENCE_THRESHOLD} -> auto-respond")
        return "respond"

    # ── Self-Correction: compliance flagged issues + retries left ──
    if compliance_notes and retry_count < MAX_RETRIES:
        logger.info(
            f"🔄 Self-correction triggered: {len(compliance_notes)} compliance issue(s), "
            f"retry {retry_count + 1}/{MAX_RETRIES}. "
            f"Issues: {', '.join(compliance_notes[:3])}"
        )
        return "draft_response"

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
