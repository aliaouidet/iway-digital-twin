"""
Node 2a: RAG Retrieval — Semantic search + cross-encoder reranking.

Pipeline:
  1. Bi-encoder (MiniLM) retrieves top-10 candidates via cosine similarity
  2. Cross-encoder (ms-marco-MiniLM) reranks candidates for higher accuracy
  3. Top-5 reranked results converted to typed RetrievedDoc objects

The parent document text (full Q&A) is used for LLM context injection
instead of the child chunk, ensuring complete context.
"""

import logging

from state import ClaimsGraphState, RetrievedDoc

logger = logging.getLogger("I-Way-Twin")

# Number of candidates to retrieve before reranking
_RERANK_CANDIDATES = 10


async def rag_retrieval_node(state: ClaimsGraphState) -> dict:
    """
    Node 2a: RAG Retrieval + Cross-Encoder Reranking.

    Retrieves top-10 candidates via bi-encoder, then reranks with
    cross-encoder to get the most accurate top-5 results.
    Uses parent document text for LLM context injection.
    """
    from backend.services.rag_service import async_retrieve_context, knowledge_store
    from backend.services.reranker import async_rerank
    from backend.config import get_settings

    settings = get_settings()
    query = state["messages"][-1].content

    logger.info(f"RAG retrieval for: {query[:60]}... (store={knowledge_store.count} entries)")

    # Early exit if vector store is empty
    if knowledge_store.count == 0:
        logger.warning("Knowledge store is empty -- RAG will return no results")
        return {
            "retrieved_docs": [],
            "rag_confidence": 0.0,
        }

    # Step 1: Bi-encoder retrieval (top-10 candidates for reranking)
    raw_results = await async_retrieve_context(query, top_k=_RERANK_CANDIDATES)

    if not raw_results:
        return {"retrieved_docs": [], "rag_confidence": 0.0}

    # Step 2: Cross-encoder reranking (top-10 → top-5)
    reranked = await async_rerank(query, raw_results, top_k=settings.RAG_TOP_K)

    logger.info(
        f"Reranked {len(raw_results)} → {len(reranked)} docs "
        f"(top rerank score: {reranked[0].get('similarity', 0):.3f})"
    )

    # Step 3: Convert to typed RetrievedDoc objects
    # Use parent document text (full Q&A) instead of child chunk for LLM context
    retrieved_docs = []
    seen_originals = set()  # Deduplicate by original Q&A ID

    for res in reranked:
        metadata = res.get("metadata", {})
        original_id = metadata.get("original_id", res.get("source_id", "unknown"))

        # Deduplicate: if we already have this Q&A, skip
        if original_id in seen_originals:
            continue
        seen_originals.add(original_id)

        # Use parent text (full Q&A) if available, otherwise use chunk
        parent_text = ""
        q = metadata.get("question", "")
        r = metadata.get("reponse", "")
        if q and r:
            parent_text = f"Question: {q}\nRéponse: {r}"
        else:
            parent_text = res["chunk_text"]

        doc = RetrievedDoc(
            content=parent_text,
            source_id=res.get("source_id", "unknown"),
            source_type=res.get("source_type", "iway_api"),
            similarity=res.get("similarity", 0.0),
            metadata=metadata,
        )
        retrieved_docs.append(doc)

    # RAG confidence = top document similarity score (from reranker)
    rag_confidence = retrieved_docs[0].similarity if retrieved_docs else 0.0

    logger.info(
        f"RAG final: {len(retrieved_docs)} unique docs "
        f"(top similarity: {rag_confidence:.2f}, threshold: {settings.RAG_SIMILARITY_THRESHOLD})"
    )

    return {
        "retrieved_docs": retrieved_docs,
        "rag_confidence": rag_confidence,
    }
