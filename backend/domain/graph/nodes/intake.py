"""
Node 1: Intake — Intent Classification (LLM-powered).

Classifies the user's latest message into one of four deterministic intents:
  - info_query:       General insurance knowledge questions
  - claim_action:     Submit/check a specific claim
  - personal_lookup:  Access personal data (dossiers, beneficiaries)
  - escalation:       User demands a human agent
"""

import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState, ClaimIntent
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


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

Reponds UNIQUEMENT avec le nom de la categorie, sans guillemets ni explication.
Par exemple: info_query"""


async def intake_node(state: ClaimsGraphState) -> dict:
    """
    Node 1: Intake & Intent Classification.

    Uses the LLM to classify the user's latest message into one of four
    deterministic intents. The classification drives the conditional edge
    that routes to the correct processing node.
    """
    last_message = state["messages"][-1]

    response = await llm.ainvoke([
        SystemMessage(content=INTAKE_SYSTEM_PROMPT),
        last_message,
    ])

    # Parse the LLM response into a ClaimIntent enum
    raw_intent = response.content.strip().lower().replace('"', '').replace("'", "")

    # Map to enum with safe fallback
    intent_map = {
        "info_query": ClaimIntent.INFO_QUERY,
        "claim_action": ClaimIntent.CLAIM_ACTION,
        "escalation": ClaimIntent.ESCALATION,
        "personal_lookup": ClaimIntent.PERSONAL_LOOKUP,
    }
    intent = intent_map.get(raw_intent, ClaimIntent.INFO_QUERY)

    logger.info(f"Intake classified intent: {intent.value} (raw: '{raw_intent}')")
    return {"intent": intent}
