"""
Knowledge Router — Knowledge base management and RAG endpoints.

Routes:
  GET  /api/v1/knowledge/stats     — Knowledge store statistics
  GET  /api/v1/knowledge/search    — RAG similarity search
  POST /api/v1/knowledge/sync      — Trigger manual sync
"""

import logging

from fastapi import APIRouter, Depends, Query

from backend.routers.auth import get_current_user
from backend.services.rag_service import retrieve_context, get_knowledge_stats

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge"])


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
    results = retrieve_context(q, top_k=top_k)
    return {
        "query": q,
        "results": results,
        "count": len(results),
        "stats": get_knowledge_stats(),
    }


@router.post("/sync")
async def trigger_sync(matricule: str = Depends(get_current_user)):
    """Manually trigger a knowledge base sync from I-Way API."""
    from backend.workers.sync_worker import sync_knowledge_direct
    result = sync_knowledge_direct()
    return {
        "status": "synced",
        "result": result,
    }
