"""
Dashboard Router — Monitoring, analytics, and admin configuration.

Routes:
  GET  /api/v1/metrics
  GET  /api/v1/logs
  GET  /api/v1/insights
  GET  /api/v1/admin/config
  PUT  /api/v1/admin/config
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.routers.auth import get_current_user, require_role

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1", tags=["Monitoring"])


# --- In-memory stores (same as original main.py) ---

SYSTEM_LOGS = [
    {"id": "L001", "timestamp": "2026-04-13 19:07:12", "user_id": "12345", "query": "Comment ajouter un beneficiaire ?", "top_similarity": 0.94, "chunks_retrieved": 3, "gen_time_ms": 820, "tokens_used": 842, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 94},
    {"id": "L002", "timestamp": "2026-04-13 19:06:55", "user_id": "12345", "query": "Quel est le delai de remboursement ?", "top_similarity": 0.88, "chunks_retrieved": 3, "gen_time_ms": 750, "tokens_used": 921, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 88},
    {"id": "L003", "timestamp": "2026-04-13 19:05:30", "user_id": "99999", "query": "Comment facturer un acte hors nomenclature ?", "top_similarity": 0.71, "chunks_retrieved": 2, "gen_time_ms": 1140, "tokens_used": 1203, "outcome": "AI_FALLBACK", "model": "gemini-2.5-flash", "confidence": 71},
    {"id": "L004", "timestamp": "2026-04-13 19:04:01", "user_id": "12345", "query": "Je veux parler a un humain", "top_similarity": 0.38, "chunks_retrieved": 1, "gen_time_ms": 2310, "tokens_used": 1842, "outcome": "HUMAN_ESCALATED", "model": "gemini-2.5-flash", "confidence": 38},
    {"id": "L005", "timestamp": "2026-04-13 19:03:44", "user_id": "12345", "query": "Prise en charge hospitaliere urgence", "top_similarity": 0.96, "chunks_retrieved": 3, "gen_time_ms": 610, "tokens_used": 703, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 96},
    {"id": "L006", "timestamp": "2026-04-13 19:02:18", "user_id": "99999", "query": "Erreur de connexion au portail prestataire", "top_similarity": 0.29, "chunks_retrieved": 1, "gen_time_ms": 3100, "tokens_used": 2102, "outcome": "ERROR", "model": "gemini-2.5-flash", "confidence": 15},
    {"id": "L007", "timestamp": "2026-04-13 19:01:05", "user_id": "12345", "query": "Quel est le plafond pour les soins dentaires ?", "top_similarity": 0.92, "chunks_retrieved": 3, "gen_time_ms": 690, "tokens_used": 780, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 92},
    {"id": "L008", "timestamp": "2026-04-13 19:00:22", "user_id": "12345", "query": "Quelle est la prime de naissance ?", "top_similarity": 0.91, "chunks_retrieved": 3, "gen_time_ms": 870, "tokens_used": 910, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 91},
    {"id": "L009", "timestamp": "2026-04-14 10:15:30", "user_id": "12345", "query": "Quels sont mes dossiers en cours ?", "top_similarity": 0.0, "chunks_retrieved": 0, "gen_time_ms": 1250, "tokens_used": 1100, "outcome": "AGENT_RESOLVED", "model": "gemini-2.5-flash", "confidence": 90},
    {"id": "L010", "timestamp": "2026-04-14 10:20:45", "user_id": "12345", "query": "Les vaccins sont-ils couverts ?", "top_similarity": 0.95, "chunks_retrieved": 3, "gen_time_ms": 580, "tokens_used": 650, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 95},
    {"id": "L011", "timestamp": "2026-04-14 11:05:12", "user_id": "12345", "query": "Comment obtenir ma carte adherent ?", "top_similarity": 0.89, "chunks_retrieved": 2, "gen_time_ms": 720, "tokens_used": 800, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 89},
    {"id": "L012", "timestamp": "2026-04-14 11:30:00", "user_id": "99999", "query": "Combien de seances de kine sont couvertes ?", "top_similarity": 0.92, "chunks_retrieved": 3, "gen_time_ms": 2100, "tokens_used": 1500, "outcome": "AGENT_RESOLVED", "model": "gemini-2.5-flash", "confidence": 92},
    {"id": "L013", "timestamp": "2026-04-14 14:22:33", "user_id": "12345", "query": "Mon remboursement est incorrect", "top_similarity": 0.25, "chunks_retrieved": 1, "gen_time_ms": 1800, "tokens_used": 1200, "outcome": "HUMAN_ESCALATED", "model": "gemini-2.5-flash", "confidence": 25},
    {"id": "L014", "timestamp": "2026-04-14 15:10:18", "user_id": "12345", "query": "Les IRM sont-elles couvertes ?", "top_similarity": 0.93, "chunks_retrieved": 3, "gen_time_ms": 650, "tokens_used": 720, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 93},
    {"id": "L015", "timestamp": "2026-04-14 16:45:55", "user_id": "12345", "query": "La FIV est-elle prise en charge ?", "top_similarity": 0.87, "chunks_retrieved": 2, "gen_time_ms": 780, "tokens_used": 850, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 87},
    {"id": "L016", "timestamp": "2026-04-14 17:00:01", "user_id": "99999", "query": "Quelles formules proposez-vous ?", "top_similarity": 0.0, "chunks_retrieved": 0, "gen_time_ms": 5000, "tokens_used": 0, "outcome": "DEGRADED", "model": "gemini-2.5-flash", "confidence": 0},
]

SYSTEM_CONFIG = {
    "rag": {
        "chunking_strategy": "semantic",
        "top_k": 3,
        "similarity_threshold": 82,
        "enable_ai_fallback": True,
        "auto_escalate_negative_sentiment": True,
    },
    "llm": {
        "primary_model": "gemini-2.5-flash",
        "temperature": 0.2,
        "system_prompt": "Tu es l'assistant virtuel I-Sante...",
    },
    "retry": {
        "max_retries": 3,
        "backoff_seconds": 2,
    },
}


# --- Pydantic Models ---

class ConfigUpdate(BaseModel):
    rag: Optional[Dict[str, Any]] = None
    llm: Optional[Dict[str, Any]] = None
    retry: Optional[Dict[str, Any]] = None


# --- Endpoints ---

@router.get("/metrics", tags=["Monitoring"])
async def get_metrics(matricule: str = Depends(get_current_user)):
    """Aggregated dashboard metrics for the monitoring UI."""
    logs = SYSTEM_LOGS
    total = len(logs)
    rag_resolved = sum(1 for l in logs if l["outcome"] == "RAG_RESOLVED")
    ai_fallback = sum(1 for l in logs if l["outcome"] == "AI_FALLBACK")
    agent_resolved = sum(1 for l in logs if l["outcome"] == "AGENT_RESOLVED")
    human_escalated = sum(1 for l in logs if l["outcome"] == "HUMAN_ESCALATED")
    errors = sum(1 for l in logs if l["outcome"] == "ERROR")
    degraded = sum(1 for l in logs if l["outcome"] == "DEGRADED")
    avg_confidence = round(sum(l["confidence"] for l in logs) / max(total, 1), 1)
    avg_response_time = round(sum(l["gen_time_ms"] for l in logs) / max(total, 1))

    from backend.routers.iway_mock import MOCK_ESCALATION_TICKETS

    return {
        "total_requests": total,
        "rag_resolved": rag_resolved,
        "agent_resolved": agent_resolved,
        "ai_fallback": ai_fallback,
        "human_escalated": human_escalated,
        "errors": errors,
        "degraded": degraded,
        "avg_confidence": avg_confidence,
        "avg_response_time_ms": avg_response_time,
        "rag_success_rate": round(rag_resolved / max(total, 1) * 100, 1),
        "agent_success_rate": round(agent_resolved / max(total, 1) * 100, 1),
        "fallback_rate": round(ai_fallback / max(total, 1) * 100, 1),
        "escalation_rate": round(human_escalated / max(total, 1) * 100, 1),
        "error_rate": round(errors / max(total, 1) * 100, 1),
        "degraded_rate": round(degraded / max(total, 1) * 100, 1),
        "open_tickets": len(MOCK_ESCALATION_TICKETS),
        "time_series": [
            {"day": "Mon", "rag_confidence": 82, "response_time": 120, "requests": 180},
            {"day": "Tue", "rag_confidence": 85, "response_time": 132, "requests": 210},
            {"day": "Wed", "rag_confidence": 79, "response_time": 101, "requests": 195},
            {"day": "Thu", "rag_confidence": 88, "response_time": 134, "requests": 230},
            {"day": "Fri", "rag_confidence": 92, "response_time": 90, "requests": 245},
            {"day": "Sat", "rag_confidence": 89, "response_time": 110, "requests": 160},
            {"day": "Sun", "rag_confidence": 90, "response_time": 105, "requests": 140},
        ]
    }


@router.get("/logs", tags=["Monitoring"])
async def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    outcome: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_similarity: Optional[float] = Query(None, ge=0, le=1),
    matricule: str = Depends(get_current_user),
):
    """Paginated system interaction logs with filters."""
    logs = list(SYSTEM_LOGS)  # Copy

    if outcome:
        logs = [l for l in logs if l["outcome"] == outcome]
    if user_id:
        logs = [l for l in logs if l["user_id"] == user_id]
    if search:
        q = search.lower()
        logs = [l for l in logs if q in l["query"].lower() or q in l["user_id"].lower()]
    if min_similarity is not None:
        logs = [l for l in logs if l["top_similarity"] >= min_similarity]

    total = len(logs)
    start = (page - 1) * page_size
    page_logs = logs[start:start + page_size]

    return {
        "items": page_logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/insights", tags=["Analytics"])
async def get_insights(matricule: str = Depends(get_current_user)):
    """AI-generated insights about knowledge base gaps and RAG performance."""
    logs = SYSTEM_LOGS
    rag_resolved = [l for l in logs if l["outcome"] == "RAG_RESOLVED"]

    return {
        "knowledge_gaps": 23,
        "rag_coverage_rate": round(len(rag_resolved) / max(len(logs), 1) * 100),
        "docs_suggested": 142,
        "failed_clusters": 18,
        "suggestions": [
            {"category": "Facturation Hors Nomenclature", "count": 342, "trend": "up", "trend_pct": 28, "priority": "high", "suggestion": "Creer des docs detailles couvrant les flux de facturation HN, les codes d'actes speciaux et les procedures d'accord prealable."},
            {"category": "Conformite RGPD", "count": 287, "trend": "up", "trend_pct": 15, "priority": "high", "suggestion": "Developper la section conformite avec les workflows de suppression en masse et les modeles DPA."},
            {"category": "Configuration SSO Entreprise", "count": 214, "trend": "stable", "trend_pct": 2, "priority": "high", "suggestion": "Ajouter des guides pas-a-pas pour la configuration SAML avec Active Directory et Google Workspace."},
            {"category": "Erreurs Webhook", "count": 178, "trend": "up", "trend_pct": 8, "priority": "medium", "suggestion": "Documenter les modes de defaillance courants des webhooks (SSL, timeout, logique de retry) avec des exemples de code."},
            {"category": "Import CSV Cas Limites", "count": 156, "trend": "down", "trend_pct": 5, "priority": "medium", "suggestion": "Enrichir la documentation d'import CSV pour couvrir les problemes d'encodage et les limites de lignes."},
            {"category": "Configuration DNS White-Label", "count": 98, "trend": "stable", "trend_pct": 1, "priority": "low", "suggestion": "Creer un guide reseau couvrant la configuration de domaine personnalise avec provisionnement SSL."},
        ],
        "fallback_categories": [
            {"name": "DNS White-Label", "count": 98},
            {"name": "Import CSV", "count": 156},
            {"name": "Erreurs Webhook", "count": 178},
            {"name": "Config SSO", "count": 214},
            {"name": "RGPD", "count": 287},
            {"name": "Auth API", "count": 342},
        ],
        "confidence_distribution": [
            {"range": "0-0.1", "count": 42}, {"range": "0.1-0.2", "count": 78},
            {"range": "0.2-0.3", "count": 120}, {"range": "0.3-0.4", "count": 180},
            {"range": "0.4-0.5", "count": 210}, {"range": "0.5-0.6", "count": 390},
            {"range": "0.6-0.7", "count": 580}, {"range": "0.7-0.8", "count": 920},
            {"range": "0.8-0.9", "count": 1840}, {"range": "0.9-1.0", "count": 3100},
        ],
    }


@router.get("/admin/config", tags=["Admin"])
async def get_admin_config(matricule: str = Depends(require_role("Admin", "Agent"))):
    return SYSTEM_CONFIG


@router.put("/admin/config", tags=["Admin"])
async def update_admin_config(data: ConfigUpdate, matricule: str = Depends(require_role("Admin"))):
    if data.rag:
        SYSTEM_CONFIG["rag"].update(data.rag)
    if data.llm:
        SYSTEM_CONFIG["llm"].update(data.llm)
    if data.retry:
        SYSTEM_CONFIG["retry"].update(data.retry)
    logger.info(f"Config updated by {matricule}")
    return {"status": "updated", "config": SYSTEM_CONFIG}
