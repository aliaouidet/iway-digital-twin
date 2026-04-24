"""
Node 2a: RAG Retrieval — Semantic search via rag_service.py.

Performs semantic similarity search against the knowledge base
and converts results into typed RetrievedDoc objects.
"""

import logging

from state import ClaimsGraphState, RetrievedDoc

logger = logging.getLogger("I-Way-Twin")


async def rag_retrieval_node(state: ClaimsGraphState) -> dict:
    """
    Node 2a: RAG Retrieval.

    Performs semantic similarity search against the knowledge base
    using the existing rag_service.py infrastructure. Converts results
    into typed RetrievedDoc objects and computes RAG confidence from
    the top similarity score.
    """
    from backend.services.rag_service import async_retrieve_context, knowledge_store
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

    # Retrieve from the existing async-safe RAG service
    raw_results = await async_retrieve_context(query, top_k=settings.RAG_TOP_K)

    # Convert raw dicts to typed RetrievedDoc objects
    retrieved_docs = []
    for res in raw_results:
        doc = RetrievedDoc(
            content=res["chunk_text"],
            source_id=res.get("source_id", "unknown"),
            source_type=res.get("source_type", "iway_api"),
            similarity=res.get("similarity", 0.0),
            metadata=res.get("metadata", {}),
        )
        retrieved_docs.append(doc)

    # RAG confidence = top document similarity score
    rag_confidence = retrieved_docs[0].similarity if retrieved_docs else 0.0

    logger.info(
        f"RAG retrieved {len(retrieved_docs)} docs "
        f"(top similarity: {rag_confidence:.2f}, threshold: {settings.RAG_SIMILARITY_THRESHOLD})"
    )

    return {
        "retrieved_docs": retrieved_docs,
        "rag_confidence": rag_confidence,
    }
