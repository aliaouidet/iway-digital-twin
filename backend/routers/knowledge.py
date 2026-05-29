"""
Knowledge Router — Knowledge base management, RAG endpoints, and HITL extraction.

Routes:
  GET  /api/v1/knowledge/stats             — Knowledge store statistics
  GET  /api/v1/knowledge/search            — RAG similarity search
  POST /api/v1/knowledge/sync              — Trigger manual sync
  POST /api/v1/knowledge/extract-knowledge — LLM-powered Q&A extraction from session
  POST /api/v1/knowledge/save-knowledge    — Save approved pairs to RAG
"""

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from backend.routers.auth import get_current_user, require_role
from backend.services.rag_service import async_retrieve_context, get_knowledge_stats

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge"])


# ── Pydantic Models for Knowledge Extraction ──────────────────

class KnowledgePair(BaseModel):
    """A single extracted knowledge pair with classification."""
    knowledge_type: Literal["general", "procedural", "personal"] = Field(
        description="Type de connaissance: general (règles universelles), procedural (méthode anonymisée), personal (données spécifiques à un adhérent)"
    )
    question: str = Field(description="Question propre et recherchable qu'un futur utilisateur poserait")
    answer: str = Field(description="Réponse correcte, complète et en français professionnel")
    topic: str = Field(description="Sujet principal: Remboursement, Bénéficiaires, Dossiers, Procédures, etc.")
    reason: str = Field(description="Explication courte de la classification choisie")


class KnowledgePairList(BaseModel):
    """List of extracted knowledge pairs."""
    pairs: List[KnowledgePair] = Field(
        description="Paires Q&R extraites (0 à 3 maximum)"
    )


class ExtractKnowledgeInput(BaseModel):
    session_id: str


class SaveKnowledgeInput(BaseModel):
    session_id: str
    pairs: List[KnowledgePair]


# ── LLM Extraction Prompt ────────────────────────────────────

EXTRACTION_PROMPT = """Tu es un extracteur de connaissances pour le système d'assurance médicale I-Way.

Analyse cette conversation entre un client et un agent d'assurance.
Extrais les paires Question/Réponse qui seraient utiles pour former l'IA.

CLASSIFICATION OBLIGATOIRE pour chaque paire:
- "general": Connaissance applicable à TOUS les adhérents (règles, plafonds, procédures, délais, conditions).
  Exemple: "Le plafond dentaire est de 600 TND par bénéficiaire par an"
  
- "procedural": La MÉTHODE utilisée par l'agent pour résoudre le problème.
  Doit être ANONYMISÉE et généralisée (pas de noms, matricules, montants spécifiques d'un adhérent).
  Exemple: "Pour vérifier le total des remboursements d'un adhérent, consulter la section Bordereaux dans son dossier"
  
- "personal": Données spécifiques à UN adhérent (montants individuels, noms, nombres de dossiers spécifiques, statuts personnels).
  Exemple: "Vous avez 4 bordereaux pour 1050 TND"

RÈGLES:
1. IGNORE les salutations (hi, bonjour, merci), remerciements, messages système ("Transfert en cours"), et messages de remplissage ("je vais regarder", "un moment").
2. Les paires "general" doivent être des vérités UNIVERSELLES de la mutuelle.
3. Les paires "procedural" doivent être ANONYMISÉES — remplace les données spécifiques par des termes génériques ("l'adhérent", "le montant", "les bordereaux de l'adhérent", etc.).
4. Signale les paires "personal" pour que l'agent sache pourquoi elles sont exclues, mais elles ne seront PAS sauvegardées.
5. La QUESTION doit être ce qu'un FUTUR utilisateur demanderait (pas le texte littéral du chat).
6. La RÉPONSE doit être en français correct et professionnel (corrige l'orthographe et la grammaire).
7. Maximum 3 paires par conversation.
8. Si la conversation ne contient AUCUNE connaissance utile, retourne un array vide.
9. Ne crée PAS de paires redondantes.

CONVERSATION:
{conversation}"""


# ── Existing Endpoints ────────────────────────────────────────

@router.get("/stats")
async def knowledge_stats(matricule: str = Depends(get_current_user)):
    """Get current knowledge store statistics."""
    return get_knowledge_stats()


@router.get("/search")
async def knowledge_search(
    q: str = Query(..., min_length=2, description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
    matricule: str = Depends(get_current_user),
):
    """
    RAG similarity search.
    Returns the top-k most relevant knowledge chunks with similarity scores.
    HITL-validated entries receive a 15% trust boost.
    """
    results = await async_retrieve_context(q, top_k=top_k)
    return {
        "query": q,
        "results": results,
        "count": len(results),
        "stats": get_knowledge_stats(),
    }


@router.post("/sync")
async def trigger_sync(matricule: str = Depends(require_role("Agent", "Admin"))):
    """Manually trigger a knowledge base sync from I-Way API."""
    from backend.workers.sync_worker import sync_knowledge_direct
    result = sync_knowledge_direct()
    return {
        "status": "synced",
        "result": result,
    }


# ── New: Knowledge Extraction ─────────────────────────────────

@router.post("/extract-knowledge")
async def extract_knowledge(
    body: ExtractKnowledgeInput,
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """
    LLM-powered knowledge extraction from a session conversation.
    
    Analyzes the full session history and returns proposed Q&A pairs,
    each classified as 'general', 'procedural', or 'personal'.
    Personal pairs are flagged but should NOT be saved.
    """
    from backend.routers.sessions import SESSIONS

    session = SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history = session.get("history", [])
    if not history:
        return {"pairs": [], "message": "Aucun historique dans cette session."}

    # ── Step 1: Filter out noise from history ──────────────────
    NOISE_ROLES = {"system"}
    GREETING_PATTERNS = {
        "hi", "hello", "bonjour", "salut", "bonsoir", "merci",
        "thanks", "ok", "d'accord", "au revoir", "bye", "bonne journée",
        "شكرا", "مرحبا",
    }

    filtered_messages = []
    for msg in history:
        if msg.get("role") in NOISE_ROLES:
            continue
        content = (msg.get("content") or "").strip()
        if len(content) < 3:
            continue
        # Skip pure greetings (exact match after lowering)
        if content.lower().strip("!., ") in GREETING_PATTERNS:
            continue
        filtered_messages.append(msg)

    if not filtered_messages:
        return {"pairs": [], "message": "Aucune connaissance utile identifiée (conversation trop courte ou uniquement des salutations)."}

    # ── Step 2: Format conversation for LLM ────────────────────
    role_labels = {
        "user": "Client",
        "assistant": "IA",
        "agent": "Agent humain",
    }
    conversation_text = "\n".join(
        f"{role_labels.get(m['role'], m['role']).upper()}: {m['content']}"
        for m in filtered_messages
    )

    # ── Step 3: LLM structured extraction ─────────────────────
    try:
        from backend.domain.graph.llm_factory import llm

        structured_llm = llm.with_structured_output(KnowledgePairList)
        result = await structured_llm.ainvoke([
            SystemMessage(content=EXTRACTION_PROMPT.replace("{conversation}", conversation_text)),
            HumanMessage(content="Extrais les paires de connaissances de cette conversation."),
        ])

        pairs = [p.model_dump() for p in result.pairs[:3]]

        logger.info(
            f"📚 Knowledge extraction for session {body.session_id}: "
            f"{len(pairs)} pair(s) extracted "
            f"(general={sum(1 for p in pairs if p['knowledge_type'] == 'general')}, "
            f"procedural={sum(1 for p in pairs if p['knowledge_type'] == 'procedural')}, "
            f"personal={sum(1 for p in pairs if p['knowledge_type'] == 'personal')})"
        )

        return {"pairs": pairs}

    except Exception as e:
        logger.error(f"❌ Knowledge extraction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"L'extraction de connaissances a échoué: {str(e)}"
        )


@router.post("/save-knowledge")
async def save_knowledge(
    body: SaveKnowledgeInput,
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """
    Save approved knowledge pairs to the RAG knowledge base.
    
    SAFETY GUARD: Rejects any pair classified as 'personal'.
    Only 'general' and 'procedural' pairs are accepted.
    """
    from backend.routers.sessions import SESSIONS
    from backend.routers.auth import MOCK_USERS
    from backend.services.rag_service import async_add_hitl_knowledge

    session = SESSIONS.get(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Safety guard: filter out personal pairs
    safe_pairs = [p for p in body.pairs if p.knowledge_type != "personal"]
    rejected_count = len(body.pairs) - len(safe_pairs)

    if rejected_count > 0:
        logger.warning(
            f"🛡️ Rejected {rejected_count} personal pair(s) from session {body.session_id}"
        )

    if not safe_pairs:
        return {
            "status": "no_pairs",
            "saved": 0,
            "rejected": rejected_count,
            "message": "Aucune paire sauvegardable (toutes étaient des données personnelles).",
        }

    # Get agent info
    user = MOCK_USERS.get(matricule, {})
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip() or "Agent"

    saved_pairs = []
    for pair in safe_pairs:
        try:
            result = await async_add_hitl_knowledge(
                session_id=body.session_id,
                question=pair.question,
                answer=pair.answer,
                agent_matricule=matricule,
                agent_name=agent_name,
                tags=[pair.topic, pair.knowledge_type],
            )
            saved_pairs.append({
                "question": pair.question,
                "topic": pair.topic,
                "knowledge_type": pair.knowledge_type,
                "result": result,
            })
            logger.info(
                f"📚 Saved {pair.knowledge_type} knowledge: "
                f"Q='{pair.question[:50]}...' topic={pair.topic}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to save pair: {e}")

    return {
        "status": "saved",
        "saved": len(saved_pairs),
        "rejected": rejected_count,
        "pairs": saved_pairs,
    }

