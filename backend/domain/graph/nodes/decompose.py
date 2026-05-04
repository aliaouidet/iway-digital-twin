"""
Node: Decompose — Multi-Intent Query Decomposition (LLM-powered).

Replaces the single-label intake_node with a multi-label decomposer.
For simple single-intent queries, returns a 1-element array (no overhead
on the opt-in fan-out path). For multi-intent queries, decomposes into
independent sub-queries that can be executed in parallel.

Backward compatible: always sets `intent` to the primary (first) sub-intent.
"""

import json
import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState, ClaimIntent
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


DECOMPOSE_SYSTEM_PROMPT = """Tu es un decomposeur de requetes pour un systeme d'assurance medicale I-Way.

Analyse le dernier message de l'utilisateur et decompose-le en sous-requetes INDEPENDANTES.

CATEGORIES DISPONIBLES:
1. "info_query" — Questions sur les regles, plafonds, delais, procedures d'assurance, numeros de support.
2. "claim_action" — Soumettre ou verifier un remboursement specifique (montants, factures, actes medicaux).
3. "escalation" — Utilisateur mecontent ou demande explicitement un agent humain.
4. "personal_lookup" — Consulter ses donnees personnelles (dossiers, beneficiaires, historique, remboursements).
5. "small_talk" — Salutations, remerciements, politesses sans requete specifique.

REGLES:
- Si le message contient UNE SEULE intention, retourne un array avec UN SEUL element.
- Si le message contient PLUSIEURS intentions distinctes, retourne un element par intention.
- Chaque sous-requete doit etre independante et auto-suffisante.
- Ne cree PAS de sous-requetes redondantes.
- Maximum 4 sous-requetes.

Retourne UNIQUEMENT un JSON array valide, sans commentaires:
[
  {"intent": "personal_lookup", "query": "Liste mes dossiers medicaux en cours"},
  {"intent": "info_query", "query": "Quel est le numero de support ?"}
]

Exemples:
- "Bonjour" -> [{"intent": "small_talk", "query": "Bonjour"}]
- "Quels sont mes dossiers ?" -> [{"intent": "personal_lookup", "query": "Quels sont mes dossiers ?"}]
- "Liste mes dossiers et donne-moi le plafond dentaire" -> [{"intent": "personal_lookup", "query": "Liste mes dossiers"}, {"intent": "info_query", "query": "Quel est le plafond dentaire ?"}]"""


# Valid intent strings for validation
_VALID_INTENTS = {"info_query", "claim_action", "escalation", "personal_lookup", "small_talk"}

# Map string -> enum
_INTENT_MAP = {
    "info_query": ClaimIntent.INFO_QUERY,
    "claim_action": ClaimIntent.CLAIM_ACTION,
    "escalation": ClaimIntent.ESCALATION,
    "personal_lookup": ClaimIntent.PERSONAL_LOOKUP,
    "small_talk": ClaimIntent.SMALL_TALK,
}


async def decompose_node(state: ClaimsGraphState) -> dict:
    """
    Decompose Node — Multi-Intent Query Decomposition.

    Uses the LLM to split a user message into independent sub-queries.
    For single-intent messages (the common case), produces a 1-element
    array and the downstream opt-in router takes the fast single-intent path.

    Returns:
        sub_intents: list of {"intent": str, "query": str} dicts
        intent: ClaimIntent enum of the primary (first) sub-intent
    """
    last_message = state["messages"][-1]

    response = await llm.ainvoke([
        SystemMessage(content=DECOMPOSE_SYSTEM_PROMPT),
        last_message,
    ])

    raw_text = response.content.strip()

    # Strip markdown code fences if the LLM wraps JSON in ```
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)

    # Parse the LLM output
    try:
        parsed = json.loads(raw_text)

        if not isinstance(parsed, list) or len(parsed) == 0:
            raise ValueError("Expected a non-empty JSON array")

        # Validate and sanitize each sub-intent
        sub_intents = []
        for item in parsed[:4]:  # Cap at 4 sub-intents
            intent_str = item.get("intent", "").strip().lower()
            query_str = item.get("query", "").strip()

            if intent_str not in _VALID_INTENTS:
                intent_str = "info_query"  # Safe fallback
            if not query_str:
                query_str = last_message.content  # Fallback to full message

            sub_intents.append({"intent": intent_str, "query": query_str})

    except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
        logger.warning(f"Decompose JSON parse failed: {e} -- raw: {raw_text[:200]}")
        # Fallback: treat as single info_query
        sub_intents = [{"intent": "info_query", "query": last_message.content}]

    # Primary intent = first sub-intent (backward compat)
    primary_intent = _INTENT_MAP.get(sub_intents[0]["intent"], ClaimIntent.INFO_QUERY)

    logger.info(
        f"Decomposed into {len(sub_intents)} sub-intent(s): "
        f"{[s['intent'] for s in sub_intents]} (primary: {primary_intent.value})"
    )

    return {
        "sub_intents": sub_intents,
        "intent": primary_intent,
    }
