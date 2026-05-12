"""
Node 2b: Claim Extraction — LLM structured extraction.

Uses the LLM to parse the user's natural-language message into
structured ClaimDetails fields (procedure_type, amount, date, provider).
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage

from state import ClaimsGraphState, ClaimDetails
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


class ClaimExtractionSchema(BaseModel):
    """Pydantic schema for LLM structured extraction."""
    procedure_type: Optional[str] = Field(
        None,
        description="Type d'acte medical (ex: soins_dentaires, optique, consultation, analyses, radiologie, hospitalisation)"
    )
    amount_claimed: Optional[float] = Field(
        None,
        description="Montant en TND"
    )
    date_of_service: Optional[str] = Field(
        None,
        description="Date au format AAAA-MM-JJ"
    )
    provider_name: Optional[str] = Field(
        None,
        description="Nom du medecin ou de la clinique"
    )


EXTRACTION_SYSTEM_PROMPT = """Tu es un extracteur de donnees structurees pour un systeme d'assurance medicale.

Analyse le message de l'utilisateur et extrais les informations suivantes si elles sont mentionnees.
Si une information n'est pas mentionnee dans le message, mets null pour ce champ.
Ne devine PAS les informations manquantes."""


async def claim_extraction_node(state: ClaimsGraphState) -> dict:
    """
    Node 2b: Claim Detail Extraction.

    Uses the LLM with Pydantic structured output to parse the user's
    natural-language message into structured ClaimDetails fields.
    """
    last_message = state["messages"][-1]

    logger.info("Extracting claim details via LLM (structured output)...")

    try:
        structured_llm = llm.with_structured_output(ClaimExtractionSchema)
        result = await structured_llm.ainvoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            last_message,
        ])

        details = ClaimDetails(
            procedure_type=result.procedure_type,
            amount_claimed=result.amount_claimed,
            date_of_service=result.date_of_service,
            provider_name=result.provider_name,
        )

        logger.info(
            f"Extracted: procedure={details.procedure_type}, "
            f"amount={details.amount_claimed}, date={details.date_of_service}, "
            f"provider={details.provider_name}"
        )

    except Exception as e:
        logger.warning(f"Claim extraction failed: {e}")
        details = ClaimDetails()

    return {"claim_details": details}

