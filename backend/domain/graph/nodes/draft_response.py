"""
Node 3: Draft Response — LLM generation with RAG + system data.

Generates a user-facing response by injecting RAG context,
extracted claim details, AND system records into the LLM prompt.
Self-assesses confidence via a CONFIDENCE: line parsed from output.
"""

import json
import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


DRAFT_SYSTEM_PROMPT = """Tu es I-Sante, l'assistant virtuel de la mutuelle I-Way Solutions.

REGLES:
1. Reponds TOUJOURS en francais.
2. Base ta reponse UNIQUEMENT sur le contexte fourni ci-dessous. Ne genere JAMAIS d'informations inventees.
3. Si le contexte ne contient pas assez d'informations pour repondre, dis-le clairement.
4. Sois professionnel, empathique et concis (3-5 phrases maximum).
5. Cite les articles ou regles pertinents quand c'est possible.
6. Si des donnees systeme (dossiers, beneficiaires) sont fournies, presente-les de maniere claire et structuree.
7. Si des sous-requetes sont listees, reponds a CHACUNE d'entre elles dans ta reponse.

{sub_intents_section}

{context_section}

{claim_section}

{records_section}

IMPORTANT -- A la fin de ta reponse, ajoute sur une NOUVELLE ligne:
CONFIDENCE: [un nombre entre 0.0 et 1.0]

Ce score reflete ta confiance dans la reponse:
- 0.9-1.0: Reponse directement confirmee par le contexte ou les donnees systeme
- 0.7-0.89: Reponse probable mais pas explicitement confirmee
- 0.5-0.69: Reponse partielle, informations manquantes
- 0.0-0.49: Impossible de repondre correctement avec le contexte disponible"""


def _parse_confidence(response_text: str) -> tuple[float, str]:
    """
    Extract the CONFIDENCE: X.XX line from the LLM response.

    Returns (confidence_float, clean_response_without_confidence_line).
    If parsing fails, returns a conservative 0.5 score.
    """
    lines = response_text.split("\n")
    confidence = 0.5  # Conservative default
    clean_lines = []

    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("CONFIDENCE:") or stripped.startswith("CONFIDENCE :"):
            try:
                val_str = stripped.split(":", 1)[1].strip()
                val_str = val_str.replace(",", ".").replace("%", "")
                parsed = float(val_str)
                if parsed > 1.0:
                    parsed = parsed / 100.0
                confidence = max(0.0, min(1.0, parsed))
            except (ValueError, IndexError):
                pass
        else:
            clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()
    return confidence, clean_text


def _fuse_confidence(
    llm_score: float,
    rag_similarity: float,
    has_db_data: bool,
    claim_details=None,
) -> float:
    """
    Hybrid Confidence Scoring — Multi-Signal Fusion.

    Combines 3 signal types with weighted averaging:
      1. RAG similarity (0.50) — objective, from vector cosine distance
      2. LLM self-assessment (0.20) — subjective, from CONFIDENCE: line
      3. Data signal (0.30) — deterministic, from DB records or field status

    When a signal is absent (e.g., no RAG docs), its weight is
    redistributed proportionally to the remaining signals.

    Returns a float between 0.0 and 1.0.
    """
    signals: list[tuple[str, float, float]] = []

    # Signal 1: RAG similarity (most reliable — grounded in vector math)
    if rag_similarity > 0:
        signals.append(("rag", rag_similarity, 0.50))

    # Signal 2: LLM self-assessment (least reliable — but still useful)
    signals.append(("llm", llm_score, 0.20))

    # Signal 3: Data completeness (deterministic — never lies)
    if has_db_data:
        # DB records are authoritative — high confidence floor
        signals.append(("db_data", 0.90, 0.30))
    elif claim_details is not None and not claim_details.missing_required_fields():
        # All claim fields present — moderate boost
        signals.append(("fields_complete", 0.70, 0.30))
    # else: no data signal → weight redistributed to other signals

    # Weighted average with dynamic weight redistribution
    total_weight = sum(w for _, _, w in signals)
    if total_weight == 0:
        return 0.5  # Conservative fallback

    fused = sum(score * weight for _, score, weight in signals) / total_weight
    return max(0.0, min(1.0, fused))


async def draft_response_node(state: ClaimsGraphState) -> dict:
    """
    Node 3: Draft Response.

    Generates a response using the LLM with injected RAG context,
    extracted claim details, AND system records from DB tool nodes.
    Parses the LLM's self-assessed confidence score to power the
    route_by_confidence conditional edge.
    """
    # -- Build the context section from retrieved docs --
    retrieved_docs = state.get("retrieved_docs") or []
    claim_details = state.get("claim_details")
    system_records = state.get("system_records") or {}

    context_section = ""
    if retrieved_docs:
        context_parts = []
        for i, doc in enumerate(retrieved_docs, 1):
            meta = doc.metadata
            q = meta.get("question", "")
            r = meta.get("reponse", doc.content)
            source_badge = "VALIDE" if doc.source_type == "hitl_validated" else "BASE"
            context_parts.append(
                f"[Document {i} -- pertinence {doc.similarity:.0%} -- {source_badge}]\n"
                f"Q: {q}\n"
                f"R: {r}"
            )
        context_section = "CONTEXTE DISPONIBLE:\n" + "\n\n".join(context_parts)
    else:
        context_section = "CONTEXTE DISPONIBLE:\nAucun document pertinent trouve dans la base de connaissances."

    # -- Build the claim details section --
    claim_section = ""
    if claim_details and any([
        claim_details.procedure_type,
        claim_details.amount_claimed,
        claim_details.date_of_service,
        claim_details.provider_name,
    ]):
        parts = []
        if claim_details.procedure_type:
            parts.append(f"Type d'acte: {claim_details.procedure_type}")
        if claim_details.amount_claimed is not None:
            parts.append(f"Montant reclame: {claim_details.amount_claimed} TND")
        if claim_details.date_of_service:
            parts.append(f"Date de l'acte: {claim_details.date_of_service}")
        if claim_details.provider_name:
            parts.append(f"Prestataire: {claim_details.provider_name}")
        claim_section = "DETAILS DE LA RECLAMATION:\n" + "\n".join(parts)

    # -- Build the system records section --
    records_section = ""
    if system_records:
        records_section = "DONNEES SYSTEME (base de donnees):\n" + json.dumps(
            system_records, indent=2, ensure_ascii=False, default=str
        )

    # -- Build the sub-intents section (multi-intent awareness) --
    sub_intents_section = ""
    sub_intents = state.get("sub_intents") or []
    if len(sub_intents) > 1:
        items = [f"- {s['query']}" for s in sub_intents]
        sub_intents_section = (
            "SOUS-REQUETES A ADRESSER (reponds a CHACUNE):\n" + "\n".join(items)
        )

    # -- Compose the full prompt --
    system_prompt = DRAFT_SYSTEM_PROMPT.format(
        sub_intents_section=sub_intents_section,
        context_section=context_section,
        claim_section=claim_section,
        records_section=records_section,
    )

    logger.info(
        f"Drafting response with {len(retrieved_docs)} docs, "
        f"claim_details={'present' if claim_section else 'none'}, "
        f"system_records={'present' if system_records else 'none'}"
    )

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        state["messages"][-1],
    ])

    raw_response = response.content.strip()

    # -- Parse LLM self-assessed confidence --
    llm_confidence, clean_response = _parse_confidence(raw_response)

    # -- Multi-Signal Confidence Fusion --
    # Combines 3 signal types to produce a more reliable score:
    #   1. RAG similarity (objective, most reliable)  — weight 0.50
    #   2. LLM self-assessment (subjective)           — weight 0.20
    #   3. Data signal: DB records or field status     — weight 0.30
    rag_confidence = state.get("rag_confidence", 0.0) or 0.0

    intent = state.get("intent")
    if intent == "small_talk":
        confidence = 1.0
        logger.info("Small talk intent detected -> bypassing fusion, setting confidence to 1.0")
    else:
        confidence = _fuse_confidence(
            llm_score=llm_confidence,
            rag_similarity=rag_confidence,
            has_db_data=bool(system_records),
            claim_details=claim_details,
        )

        logger.info(
            f"Confidence fusion: RAG={rag_confidence:.2f}, LLM={llm_confidence:.2f} "
            f"-> fused={confidence:.2f}"
        )

    # Track which tools/paths were used
    tools_used = []
    if retrieved_docs:
        tools_used.append("rag_retrieval")
    if claim_details and claim_details.procedure_type:
        tools_used.append("claim_extraction")
    if "dossiers" in system_records:
        tools_used.append("dossier_lookup")
    if "beneficiaires" in system_records:
        tools_used.append("beneficiary_lookup")

    logger.info(f"Draft ready -- confidence: {confidence:.2f}, length: {len(clean_response)} chars")

    return {
        "draft_response": clean_response,
        "confidence": confidence,
        "tools_called": tools_used,
    }
