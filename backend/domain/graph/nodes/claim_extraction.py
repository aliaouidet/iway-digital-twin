"""
Node 2b: Claim Extraction — LLM structured extraction.

Uses the LLM to parse the user's natural-language message into
structured ClaimDetails fields (procedure_type, amount, date, provider).
"""

import json
import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState, ClaimDetails
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


EXTRACTION_SYSTEM_PROMPT = """Tu es un extracteur de donnees structurees pour un systeme d'assurance medicale.

Analyse le message de l'utilisateur et extrais les informations suivantes si elles sont mentionnees.
Retourne UNIQUEMENT du JSON valide, sans commentaires ni texte supplementaire.

Format de sortie EXACT:
{
  "procedure_type": "type d'acte medical (ex: soins_dentaires, optique, consultation, analyses, radiologie, hospitalisation) ou null",
  "amount_claimed": nombre en TND ou null,
  "date_of_service": "date au format AAAA-MM-JJ ou null",
  "provider_name": "nom du medecin ou de la clinique ou null"
}

Si une information n'est pas mentionnee dans le message, mets null pour ce champ.
Ne devine PAS les informations manquantes."""


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def claim_extraction_node(state: ClaimsGraphState) -> dict:
    """
    Node 2b: Claim Detail Extraction.

    Uses the LLM to parse the user's natural-language message into
    structured ClaimDetails fields. Handles malformed JSON gracefully
    with a fallback to empty ClaimDetails.
    """
    last_message = state["messages"][-1]

    logger.info("Extracting claim details via LLM...")

    response = await llm.ainvoke([
        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
        last_message,
    ])

    raw_text = response.content.strip()

    # Strip markdown code fences if the LLM wraps JSON in ```
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)

    # Parse LLM output as JSON
    try:
        parsed = json.loads(raw_text)

        details = ClaimDetails(
            procedure_type=parsed.get("procedure_type"),
            amount_claimed=_safe_float(parsed.get("amount_claimed")),
            date_of_service=parsed.get("date_of_service"),
            provider_name=parsed.get("provider_name"),
        )

        logger.info(
            f"Extracted: procedure={details.procedure_type}, "
            f"amount={details.amount_claimed}, date={details.date_of_service}, "
            f"provider={details.provider_name}"
        )

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Claim extraction JSON parse failed: {e} -- raw: {raw_text[:200]}")
        details = ClaimDetails()

    return {"claim_details": details}
