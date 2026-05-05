"""
Cross-Encoder Reranker — Second-stage relevance scoring.

After the bi-encoder (MiniLM) retrieves top-K candidates via cosine
similarity, this cross-encoder jointly encodes (query, document) pairs
to produce much more accurate relevance scores.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (22MB, fast, multilingual)

Usage:
    from backend.services.reranker import async_rerank
    reranked = await async_rerank(query, documents, top_k=5)
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("I-Way-Twin")

# Lazy-loaded cross-encoder model
_cross_encoder = None
_reranker_available = False

# Dedicated thread pool for CPU-bound reranking
_rerank_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rerank")

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_cross_encoder():
    """Lazy-load the cross-encoder model."""
    global _cross_encoder, _reranker_available

    if _cross_encoder is not None:
        return _cross_encoder

    try:
        from sentence_transformers import CrossEncoder

        logger.info(f"📦 Loading cross-encoder: {CROSS_ENCODER_MODEL}...")
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL, max_length=512)
        _reranker_available = True
        logger.info(f"✅ Cross-encoder loaded")
        return _cross_encoder

    except Exception as e:
        _reranker_available = False
        logger.warning(f"⚠️ Cross-encoder unavailable (reranking disabled): {e}")
        return None


def rerank(query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Rerank documents using the cross-encoder (synchronous).

    Args:
        query: The user's search query
        documents: List of dicts with at least 'chunk_text' key
        top_k: Number of top results to return

    Returns:
        Reranked list of documents with updated 'similarity' scores
    """
    encoder = _get_cross_encoder()

    if encoder is None or not documents:
        return documents[:top_k]

    # Build (query, document) pairs for cross-encoder
    pairs = [(query, doc.get("chunk_text", "")) for doc in documents]

    try:
        # Cross-encoder scores: higher = more relevant
        scores = encoder.predict(pairs)

        # Attach scores and sort
        scored_docs = []
        for doc, score in zip(documents, scores):
            doc_copy = dict(doc)
            doc_copy["rerank_score"] = float(score)
            # Normalize score to [0, 1] range using sigmoid-like mapping
            normalized = 1.0 / (1.0 + pow(2.718281828, -float(score)))
            doc_copy["similarity"] = round(normalized, 4)
            scored_docs.append(doc_copy)

        # Sort by rerank score descending
        scored_docs.sort(key=lambda d: d["rerank_score"], reverse=True)

        return scored_docs[:top_k]

    except Exception as e:
        logger.warning(f"⚠️ Reranking failed: {e} — returning original order")
        return documents[:top_k]


async def async_rerank(query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Async-safe reranking — runs cross-encoder in dedicated thread pool.

    Use this in all FastAPI/WebSocket handlers.
    """
    if not documents:
        return []

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _rerank_pool,
        lambda: rerank(query, documents, top_k)
    )


def is_reranker_available() -> bool:
    """Check if the cross-encoder model is loaded and available."""
    return _reranker_available
