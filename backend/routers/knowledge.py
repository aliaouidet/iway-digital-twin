"""
Knowledge Router — Knowledge base management, RAG endpoints, and HITL extraction.

Routes:
  GET  /api/v1/knowledge/stats             — Knowledge store statistics
  GET  /api/v1/knowledge/search            — RAG similarity search
  POST /api/v1/knowledge/sync              — Trigger manual sync
  POST /api/v1/knowledge/extract-knowledge — LLM-powered Q&A extraction from session
  POST /api/v1/knowledge/save-knowledge    — Save approved pairs to RAG
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.routers.auth import get_current_user, require_role
from backend.database.connection import get_db
from backend.services.rag_service import async_retrieve_context, get_knowledge_stats
from backend.services.pii_guard import redact_identifiers

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
    from backend.routers.auth import resolve_user
    from backend.services.rag_service import async_add_hitl_with_dedup

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
    user = await resolve_user(matricule) or {}
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip() or "Agent"

    saved_pairs = []
    for pair in safe_pairs:
        try:
            result = await async_add_hitl_with_dedup(
                session_id=body.session_id,
                question=redact_identifiers(pair.question),
                answer=redact_identifiers(pair.answer),
                agent_matricule=matricule,
                agent_name=agent_name,
                tags=[pair.topic, pair.knowledge_type],
                origin="resolve",
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


class CreateArticleInput(BaseModel):
    """A KB article authored directly (e.g. from an AI-Insights knowledge gap)."""
    question: str = Field(min_length=3, description="Searchable question a user would ask")
    answer: str = Field(min_length=3, description="Canonical answer in professional French")
    topic: str = Field(default="Insights", description="Topic/category label")


@router.post("/articles")
async def create_article(
    body: CreateArticleInput,
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """Author a single general KB article directly (no chat session required).

    Backs the AI-Insights "Create KB article" action: an admin turns a recurring
    knowledge gap into a permanent answer. Reuses async_add_hitl_knowledge with a
    synthetic source id so the entry is auditable like any HITL contribution.
    """
    from backend.routers.auth import resolve_user
    from backend.services.rag_service import async_add_hitl_with_dedup

    user = await resolve_user(matricule) or {}
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip() or "Admin"

    try:
        result = await async_add_hitl_with_dedup(
            session_id="insights-manual",
            question=redact_identifiers(body.question.strip()),
            answer=redact_identifiers(body.answer.strip()),
            agent_matricule=matricule,
            agent_name=agent_name,
            tags=[body.topic, "general"],
            origin="insights",
        )
        logger.info(f"📚 KB article created from Insights by {matricule}: Q='{body.question[:50]}'")
        return {"status": "saved", "question": body.question, "topic": body.topic, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create KB article: {e}")
        raise HTTPException(status_code=500, detail="Failed to save the article.")


# ── Governance: HITL entry CRUD (admin curation) ──────────────
# Operates on langchain_pg_embedding filtered to hitl_validated — the same table
# reembed_knowledge_base maintains via raw SQL. CAST() is used (not ::) so the
# `:` never collides with SQLAlchemy bindparams, and CAST(id AS text) works
# whether the PK column is uuid or varchar across PGVector versions.

class EntryUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    tags: Optional[List[str]] = None


class ConflictResolution(BaseModel):
    action: Literal["accept", "reject"]


def _entry_row_to_dict(row) -> dict:
    rid, document, meta = row
    meta = meta or {}
    return {
        "id": str(rid),
        "source_id": meta.get("source_id"),
        "question": meta.get("question") or document,
        "answer": meta.get("reponse"),
        "tags": meta.get("tags", []),
        "origin": meta.get("origin", "resolve"),
        "status": meta.get("status", "active"),
        "agent_name": meta.get("agent_name"),
        "created_at": meta.get("created_at") or meta.get("validated_at"),
        "updated_at": meta.get("updated_at"),
        "conflicts_with": meta.get("conflicts_with"),
    }


@router.get("/health")
async def kb_health(
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """KB-health snapshot (counts by lifecycle status) for the curation dashboard."""
    try:
        rows = (await db.execute(text(
            "SELECT COALESCE(cmetadata->>'status','active') AS st, COUNT(*) "
            "FROM langchain_pg_embedding "
            "WHERE cmetadata->>'source_type' = 'hitl_validated' GROUP BY 1"
        ))).fetchall()
    except Exception as e:
        logger.warning(f"KB health failed (PGVector unavailable?): {e}")
        return {"total": 0, "by_status": {}}
    by_status = {(r[0] or "active"): int(r[1]) for r in rows}
    return {
        "total": sum(by_status.values()),
        "active": by_status.get("active", 0),
        "conflict": by_status.get("conflict", 0),
        "retired": by_status.get("retired", 0),
        "needs_review": by_status.get("needs_review", 0),
        "by_status": by_status,
    }


@router.get("/entries")
async def list_entries(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    matricule: str = Depends(require_role("Agent", "Admin")),
):
    """List HITL knowledge entries with provenance + usage stats (curation view)."""
    from backend.services import kb_feedback
    try:
        rows = (await db.execute(text(
            "SELECT uuid, document, cmetadata FROM langchain_pg_embedding "
            "WHERE cmetadata->>'source_type' = 'hitl_validated' "
            "ORDER BY cmetadata->>'created_at' DESC NULLS LAST LIMIT 500"
        ))).fetchall()
    except Exception as e:
        logger.warning(f"KB entries list failed (PGVector unavailable?): {e}")
        return {"entries": [], "total": 0}

    entries = [_entry_row_to_dict(r) for r in rows]
    if status:
        entries = [e for e in entries if e["status"] == status]
    # One concurrent batch of per-entry usage stats, not N serial Redis reads.
    targeted = [e for e in entries if e.get("source_id")]
    stats = await asyncio.gather(*(kb_feedback.get_stats_async(e["source_id"]) for e in targeted))
    for e, s in zip(targeted, stats):
        e["usage"] = s
    return {"entries": entries, "total": len(entries)}


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str, body: EntryUpdate,
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(require_role("Admin")),
):
    """Edit a HITL entry — updates the document + metadata and re-embeds the vector."""
    from backend.services.rag_service import async_embed_text
    row = (await db.execute(text(
        "SELECT cmetadata FROM langchain_pg_embedding WHERE CAST(uuid AS text) = :id"
    ), {"id": entry_id})).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")

    meta = row[0] or {}
    question = redact_identifiers(body.question) if body.question is not None else meta.get("question", "")
    answer = redact_identifiers(body.answer) if body.answer is not None else meta.get("reponse", "")
    document = f"Question: {question}\nRéponse: {answer}"
    vector = await async_embed_text(document)

    # jsonb_set only the changed keys (not a full cmetadata replace) so a
    # concurrent status change — e.g. resolve-conflict — is never clobbered.
    updates = {
        "question": question,
        "reponse": answer,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.tags is not None:
        updates["tags"] = body.tags
    expr, params = "cmetadata", {"doc": document, "emb": str(list(vector)), "id": entry_id}
    for i, (key, val) in enumerate(updates.items()):
        # jsonb_set path is text[] → asyncpg needs a Python list ([key]), not the
        # '{key}' array-literal string (which it rejects as non-iterable).
        expr = f"jsonb_set({expr}, CAST(:p{i} AS text[]), CAST(:v{i} AS jsonb))"
        params[f"p{i}"] = [key]
        params[f"v{i}"] = json.dumps(val)

    await db.execute(text(
        f"UPDATE langchain_pg_embedding SET document = :doc, "
        f"embedding = CAST(:emb AS vector), cmetadata = {expr} "
        f"WHERE CAST(uuid AS text) = :id"
    ), params)
    return {"status": "updated", "id": entry_id}


async def _set_entry_status(db: AsyncSession, entry_id: str, status: str) -> int:
    res = await db.execute(text(
        "UPDATE langchain_pg_embedding "
        "SET cmetadata = jsonb_set(cmetadata, '{status}', CAST(:st AS jsonb)) "
        "WHERE CAST(uuid AS text) = :id"
    ), {"st": json.dumps(status), "id": entry_id})
    return res.rowcount


@router.post("/entries/{entry_id}/retire")
async def retire_entry(entry_id: str, db: AsyncSession = Depends(get_db),
                       matricule: str = Depends(require_role("Admin"))):
    if not await _set_entry_status(db, entry_id, "retired"):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "retired", "id": entry_id}


@router.post("/entries/{entry_id}/restore")
async def restore_entry(entry_id: str, db: AsyncSession = Depends(get_db),
                        matricule: str = Depends(require_role("Admin"))):
    if not await _set_entry_status(db, entry_id, "active"):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "active", "id": entry_id}


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str, db: AsyncSession = Depends(get_db),
                       matricule: str = Depends(require_role("Admin"))):
    res = await db.execute(text(
        "DELETE FROM langchain_pg_embedding WHERE CAST(uuid AS text) = :id"
    ), {"id": entry_id})
    if not res.rowcount:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "deleted", "id": entry_id}


@router.post("/entries/{entry_id}/resolve-conflict")
async def resolve_conflict(
    entry_id: str, body: ConflictResolution,
    db: AsyncSession = Depends(get_db),
    matricule: str = Depends(require_role("Admin")),
):
    """Accept a conflicting entry (activate it + supersede the old) or reject it (retire)."""
    row = (await db.execute(text(
        "SELECT cmetadata FROM langchain_pg_embedding WHERE CAST(uuid AS text) = :id"
    ), {"id": entry_id})).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")

    if body.action == "reject":
        await _set_entry_status(db, entry_id, "retired")
        return {"status": "rejected", "id": entry_id}

    await _set_entry_status(db, entry_id, "active")
    conflicts_with = (row[0] or {}).get("conflicts_with")
    if conflicts_with:
        await db.execute(text(
            "UPDATE langchain_pg_embedding "
            "SET cmetadata = jsonb_set(cmetadata, '{status}', CAST(:st AS jsonb)) "
            "WHERE cmetadata->>'source_id' = :sid"
        ), {"st": json.dumps("superseded"), "sid": conflicts_with})
    return {"status": "accepted", "id": entry_id, "superseded": conflicts_with}

