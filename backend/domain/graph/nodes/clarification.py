"""
Node 4a: Clarification — Ask user for missing claim fields.

When the draft has low confidence AND ClaimDetails is missing
required fields, this node asks the user to provide specific
missing information instead of silently handing off.
"""

import logging

from state import ClaimsGraphState, ClaimDetails

logger = logging.getLogger("I-Way-Twin")


async def clarification_node(state: ClaimsGraphState) -> dict:
    """
    Node 4a: Active Clarification Loop.

    The user's next message will re-enter the graph at START, get
    re-classified as claim_action, and the merge_claim_details reducer
    will progressively fill in the gaps.
    """
    claim_details = state.get("claim_details") or ClaimDetails()
    missing = claim_details.missing_required_fields()

    # Build a natural, specific clarification message
    if len(missing) == 1:
        missing_text = missing[0]
        clarification = (
            f"Pour traiter votre demande de remboursement, j'ai encore besoin "
            f"d'une information : le **{missing_text}**. "
            f"Pourriez-vous me le fournir ?"
        )
    else:
        items = ", ".join(f"**{m}**" for m in missing[:-1])
        last = f"**{missing[-1]}**"
        clarification = (
            f"Pour traiter votre demande, il me manque quelques informations : "
            f"{items} et {last}. "
            f"Pourriez-vous me les fournir ?"
        )

    logger.info(f"Clarification requested for {len(missing)} missing fields: {missing}")

    return {
        "final_response": clarification,
        "claim_status": "active",  # Stay active — waiting for user's next message
    }
