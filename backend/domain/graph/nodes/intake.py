"""
Node 1: Intake — Intent Classification (LLM-powered).

Classifies the user's latest message into one of four deterministic intents:
  - info_query:       General insurance knowledge questions
  - claim_action:     Submit/check a specific claim
  - personal_lookup:  Access personal data (dossiers, beneficiaries)
  - escalation:       User demands a human agent
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage

from state import ClaimsGraphState, ClaimIntent
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


class IntentSchema(BaseModel):
    """Pydantic schema for intent classification."""
    intent: Literal["info_query", "claim_action", "escalation", "personal_lookup", "small_talk"] = Field(
        description="The classified intent category"
    )


INTAKE_SYSTEM_PROMPT = """Tu es un classificateur d'intentions pour un systeme d'assurance medicale I-Way.

Analyse le dernier message de l'utilisateur et classifie-le dans EXACTEMENT UNE de ces categories:

1. "info_query" — Questions generales sur les regles, plafonds, delais, procedures ou couvertures d'assurance.
   Exemples: "Quel est le plafond dentaire ?", "Les IRM sont-elles couvertes ?", "Quel delai de remboursement ?"

2. "claim_action" — L'utilisateur veut soumettre, verifier ou agir sur un remboursement ou une prestation specifique. 
   Il mentionne des montants, des dates, des factures, ou des actes medicaux concrets.
   Exemples: "J'ai une facture de 250 TND pour une consultation", "Mon remboursement de mars"

3. "escalation" — L'utilisateur est mecontent, frustre, en colere, ou demande explicitement un agent humain.
   Exemples: "Je veux parler a un humain", "C'est inacceptable", "Votre service est nul"

4. "personal_lookup" — L'utilisateur veut consulter ses propres donnees personnelles (dossiers, beneficiaires, historique).
   Exemples: "Quels sont mes dossiers ?", "Qui est sur mon contrat ?", "Mon historique de soins"

5. "small_talk" — Salutations, remerciements, ou politesses basiques sans requete specifique.
   Exemples: "Bonjour", "Salut", "Merci beaucoup", "Au revoir" """


# Map string -> enum
_INTENT_MAP = {
    "info_query": ClaimIntent.INFO_QUERY,
    "claim_action": ClaimIntent.CLAIM_ACTION,
    "escalation": ClaimIntent.ESCALATION,
    "personal_lookup": ClaimIntent.PERSONAL_LOOKUP,
    "small_talk": ClaimIntent.SMALL_TALK,
}


async def intake_node(state: ClaimsGraphState) -> dict:
    """
    Node 1: Intake & Intent Classification.

    Uses the LLM with Pydantic structured output to classify the user's
    latest message into one of the deterministic intents.
    """
    last_message = state["messages"][-1]

    try:
        structured_llm = llm.with_structured_output(IntentSchema)
        result = await structured_llm.ainvoke([
            SystemMessage(content=INTAKE_SYSTEM_PROMPT),
            last_message,
        ])

        intent = _INTENT_MAP.get(result.intent, ClaimIntent.INFO_QUERY)
        logger.info(f"Intake classified intent: {intent.value} (structured: '{result.intent}')")

    except Exception as e:
        logger.warning(f"Intake structured output failed: {e}, defaulting to info_query")
        intent = ClaimIntent.INFO_QUERY

    return {"intent": intent}

