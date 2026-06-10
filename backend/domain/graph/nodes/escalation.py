"""
Node 7: Escalation — Immediate ticket creation.

Triggered when the user explicitly demands a human agent or is
detected as angry/frustrated.

When IWAY_USE_REAL_API is enabled, the escalation also files a formal
réclamation in the real I-Way system (reclamationWS.createReclamation) so the
case is tracked there, not just in the in-memory handoff queue. On any failure
(or when the real API is off) it falls back to the in-memory stub ticket, so
escalation always works.
"""

import re
import logging

from state import ClaimsGraphState
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

_STUB_RESPONSE = (
    "Je comprends votre frustration. Un agent humain va prendre "
    "en charge votre conversation dans les plus brefs delais. "
    "Votre position dans la file : 1."
)

# Filing a réclamation is a PRODUCTION WRITE. It must only happen when the user
# EXPLICITLY asks to file one — never on anger detection or a plain request for
# a human, both of which also land on this node via intent classification.
_EXPLICIT_COMPLAINT_RE = re.compile(
    r"(d[ée]poser|porter|faire|introduire|soumettre|enregistrer|ouvrir)\s+"
    r"(une\s+|ma\s+|la\s+)?(r[ée]clamation|plainte)",
    re.IGNORECASE,
)


def wants_formal_complaint(message: str) -> bool:
    """True only for an explicit 'file a complaint' request."""
    return bool(_EXPLICIT_COMPLAINT_RE.search(message or ""))


async def escalation_node(state: ClaimsGraphState) -> dict:
    """
    Node 2c: Escalation Handler.

    Unlike handoff_node, this is an immediate, explicit escalation. When the real
    I-Way API is enabled it creates a réclamation (formal complaint record) and
    surfaces its number to the user.
    """
    reason = state["messages"][-1].content
    matricule = state.get("matricule", "")
    logger.info(f"Escalation triggered: {reason[:60]}...")

    ticket = None
    final_response = _STUB_RESPONSE

    if settings.IWAY_USE_REAL_API and matricule and wants_formal_complaint(reason):
        try:
            from backend.services import iway_soap_client as soap

            rec = await soap.create_reclamation(
                matricule=matricule,
                titre="Réclamation déposée via l'assistant I-Santé",
                description=reason,
                nature="Escalade",
            )
            if rec is not None:
                # The réclamation EXISTS server-side even if the numéro is
                # assigned asynchronously — always acknowledge it, or the user
                # retries and files a duplicate.
                numero = rec.get("numero")
                ticket = {
                    "case_id": numero or "REC-EN-ATTENTE",
                    "type": "reclamation",
                    "queue_position": 1,
                    "estimated_wait": "5 minutes",
                }
                if numero:
                    final_response = (
                        f"Votre réclamation a bien été enregistrée sous le numéro **{numero}**. "
                        "Un agent humain va prendre en charge votre demande dans les plus brefs délais."
                    )
                else:
                    final_response = (
                        "Votre réclamation a bien été enregistrée (le numéro de suivi vous sera "
                        "communiqué par un agent). Un agent humain va prendre en charge votre "
                        "demande dans les plus brefs délais."
                    )
                logger.info(f"Escalation filed réclamation {numero or '(numéro en attente)'} (real API)")
        except Exception as e:
            logger.warning(f"⚠️ Real réclamation creation failed ({e}); using stub ticket")

    if ticket is None:
        ticket = {
            "case_id": "ESC-STUB-001",
            "queue_position": 1,
            "estimated_wait": "5 minutes",
        }

    return {
        "escalation_ticket": ticket,
        "escalation_reason": reason,
        "claim_status": "pending_human",
        "final_response": final_response,
    }
