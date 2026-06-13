"""
Node: Decompose — Multi-Intent Query Decomposition (LLM-powered).

Replaces the single-label intake_node with a multi-label decomposer.
For simple single-intent queries, returns a 1-element array (no overhead
on the opt-in fan-out path). For multi-intent queries, decomposes into
independent sub-queries that can be executed in parallel.

Backward compatible: always sets `intent` to the primary (first) sub-intent.
"""

import logging
from typing import List, Literal

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage

from backend.domain.state import ClaimsGraphState, ClaimIntent
from backend.domain.graph.llm_factory import llm
from backend.domain.graph.semantic_router import classify_intent

logger = logging.getLogger("I-Way-Twin")


class SubIntent(BaseModel):
    """A single decomposed sub-intent."""
    intent: Literal["info_query", "claim_action", "escalation", "personal_lookup", "provider_search", "small_talk"] = Field(
        description="The classified intent category"
    )
    query: str = Field(
        description="The standalone sub-query text"
    )


class SubIntentList(BaseModel):
    """List of decomposed sub-intents."""
    sub_intents: List[SubIntent] = Field(
        description="Array of decomposed sub-intents (1 for single-intent, up to 4 for multi-intent)"
    )


DECOMPOSE_SYSTEM_PROMPT = """Tu es un decomposeur de requetes pour un systeme d'assurance medicale I-Way.

Analyse le dernier message de l'utilisateur et decompose-le en sous-requetes INDEPENDANTES.

CATEGORIES DISPONIBLES:
1. "info_query" — Questions sur les regles, plafonds, delais, procedures d'assurance, numeros de support.
2. "claim_action" — Soumettre une NOUVELLE demande de remboursement (montants, factures, actes medicaux a declarer). (Verifier/suivre un remboursement deja soumis = "personal_lookup".)
3. "escalation" — Utilisateur mecontent, demande explicitement un agent humain, ou veut DEPOSER une nouvelle reclamation. (Demander le STATUT d'une reclamation existante = "personal_lookup", PAS "escalation".)
4. "personal_lookup" — Consulter ses donnees personnelles (dossiers, beneficiaires, historique, remboursements, factures, plafonds/consommation, statut/suivi de ses reclamations existantes, detail d'un dossier precis).
5. "provider_search" — Chercher un prestataire de soins conventionne (medecin, clinique, pharmacie, laboratoire) par specialite et/ou localisation. (PAS ses propres donnees.)
6. "small_talk" — Salutations, remerciements, politesses sans requete specifique.

REGLES:
- Si le message contient UNE SEULE intention, retourne un array avec UN SEUL element.
- Si le message contient PLUSIEURS intentions distinctes, retourne un element par intention.
- Chaque sous-requete doit etre independante et auto-suffisante.
- Ne cree PAS de sous-requetes redondantes.
- Maximum 4 sous-requetes.

Exemples:
- "Bonjour" -> [{"intent": "small_talk", "query": "Bonjour"}]
- "Quels sont mes dossiers ?" -> [{"intent": "personal_lookup", "query": "Quels sont mes dossiers ?"}]
- "Liste mes dossiers et donne-moi le plafond dentaire" -> [{"intent": "personal_lookup", "query": "Liste mes dossiers"}, {"intent": "info_query", "query": "Quel est le plafond dentaire ?"}]
- "Ou en sont mes reclamations ?" -> [{"intent": "personal_lookup", "query": "Ou en sont mes reclamations ?"}]
- "Trouve-moi un cardiologue conventionne a Sousse" -> [{"intent": "provider_search", "query": "Trouve-moi un cardiologue conventionne a Sousse"}]"""


# Map string -> enum
_INTENT_MAP = {
    "info_query": ClaimIntent.INFO_QUERY,
    "claim_action": ClaimIntent.CLAIM_ACTION,
    "escalation": ClaimIntent.ESCALATION,
    "personal_lookup": ClaimIntent.PERSONAL_LOOKUP,
    "provider_search": ClaimIntent.PROVIDER_SEARCH,
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
    user_text = last_message.content

    # ── FAST PATH: Semantic Router (sub-100ms, no LLM call) ──
    # For short, single-intent messages, the semantic router can
    # classify intent without an LLM call. Only falls back to the
    # LLM decomposer when uncertain or message may be multi-intent.
    word_count = len(user_text.split())
    # classify_intent embeds the text (CPU-bound) — run off the event loop so
    # other sessions aren't stalled while this one is classified.
    import anyio
    router_intent, router_confidence = await anyio.to_thread.run_sync(classify_intent, user_text)

    if router_intent is not None and router_confidence >= 0.80 and word_count <= 20:
        # High-confidence single-intent — skip LLM entirely
        primary_intent = _INTENT_MAP.get(router_intent, ClaimIntent.INFO_QUERY)
        sub_intents = [{"intent": router_intent, "query": user_text}]

        logger.info(
            f"🧭 Semantic router classified: {router_intent} "
            f"(confidence={router_confidence:.3f}, skipped LLM decomposer)"
        )

        return {
            "sub_intents": sub_intents,
            "intent": primary_intent,
        }

    # ── SLOW PATH: LLM Decomposer (multi-intent, low router confidence) ──
    logger.info(
        f"🧠 LLM decomposer activated (router={router_intent}/{router_confidence:.2f}, "
        f"words={word_count})"
    )

    try:
        structured_llm = llm.with_structured_output(SubIntentList)
        result = await structured_llm.ainvoke([
            SystemMessage(content=DECOMPOSE_SYSTEM_PROMPT),
            last_message,
        ])

        sub_intents = [{"intent": si.intent, "query": si.query} for si in result.sub_intents[:4]]

        if not sub_intents:
            raise ValueError("Empty sub_intents list")

    except Exception as e:
        logger.warning(f"Decompose structured output failed: {e}")
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

