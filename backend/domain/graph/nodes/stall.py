"""
Node 6: Stall — Keep user engaged while pending human review.

Intercepts messages when claim_status == "pending_human" and
generates friendly small talk instead of re-running the full pipeline.
"""

import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


STALL_SYSTEM_PROMPT = """Tu es I-Sante, l'assistant virtuel de la mutuelle I-Way Solutions.

CONTEXTE: Le dossier de cet utilisateur est actuellement en cours de verification par un superviseur humain. 
Tu ne dois PAS tenter de repondre a des questions sur son dossier en cours.

TON ROLE pendant l'attente:
1. Rappeler poliment que le dossier est en cours de traitement.
2. Etre chaleureux et empathique pour que l'utilisateur ne se sente pas abandonne.
3. Proposer des sujets utiles pendant l'attente:
   - "Vos coordonnees sont-elles a jour ?"
   - "Souhaitez-vous en savoir plus sur nos garanties ?"
   - "Avez-vous des questions generales sur le fonctionnement de votre mutuelle ?"
4. Si l'utilisateur pose une question generale (non liee a son dossier), tu PEUX y repondre normalement.
5. Reponds en 2-3 phrases maximum. Sois concis et naturel.

Reponds TOUJOURS en francais."""


async def stall_node(state: ClaimsGraphState) -> dict:
    """
    Node 6: Stall (Active Engagement While Pending Human).

    When claim_status == "pending_human" and the user sends a new message,
    this node intercepts it with friendly engagement.
    """
    last_message = state["messages"][-1]

    logger.info(f"Stall node -- user message while pending_human: {last_message.content[:60]}...")

    response = await llm.ainvoke([
        SystemMessage(content=STALL_SYSTEM_PROMPT),
        last_message,
    ])

    stall_response = response.content.strip()

    logger.info(f"Stall response generated ({len(stall_response)} chars)")

    return {
        "final_response": stall_response,
        # claim_status stays "pending_human" — not changed here
    }
