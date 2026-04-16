"""
RAG Service — Embedding, vector storage, and similarity search.

Supports two modes:
  1. In-memory (numpy cosine similarity) — works without PostgreSQL
  2. pgvector (SQL-based vector search) — used with Docker Compose

The service uses sentence-transformers for local embedding generation.
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# --- Lazy-loaded embedding model (loads once, caches forever) ---
_model = None


def _get_model():
    """Lazy-load the sentence-transformers model to avoid slow startup."""
    global _model
    if _model is None:
        logger.info(f"📦 Loading embedding model: {settings.EMBEDDING_MODEL}...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info(f"✅ Embedding model loaded ({settings.EMBEDDING_DIMENSIONS}d)")
    return _model


def embed_text(text: str) -> List[float]:
    """Embed a single text string into a dense vector."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch embed multiple texts (more efficient than one-by-one)."""
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return embeddings.tolist()


# ==============================================================
# IN-MEMORY VECTOR STORE (fallback when PostgreSQL is unavailable)
# ==============================================================

class InMemoryVectorStore:
    """Simple vector store using numpy for cosine similarity.
    
    Used for local development/demo without Docker.
    Same interface as the pgvector implementation for easy swapping.
    """

    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self._dirty = True  # Flag to rebuild index

    def upsert(self, source_id: str, source_type: str, chunk_text: str,
               embedding: List[float], metadata: Dict[str, Any] = None):
        """Insert or update a knowledge entry."""
        # Check if exists
        for i, entry in enumerate(self.entries):
            if entry["source_id"] == source_id and entry["source_type"] == source_type:
                # Update
                self.entries[i] = {
                    "source_id": source_id,
                    "source_type": source_type,
                    "chunk_text": chunk_text,
                    "embedding": embedding,
                    "metadata": metadata or {},
                    "last_synced_at": datetime.now(timezone.utc).isoformat(),
                }
                self._dirty = True
                return "updated"

        # Insert
        self.entries.append({
            "source_id": source_id,
            "source_type": source_type,
            "chunk_text": chunk_text,
            "embedding": embedding,
            "metadata": metadata or {},
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        })
        self._dirty = True
        return "inserted"

    def _rebuild_index(self):
        """Rebuild the numpy embedding matrix for fast similarity search."""
        if self.entries:
            self.embeddings = np.array([e["embedding"] for e in self.entries])
        else:
            self.embeddings = None
        self._dirty = False

    def search(self, query_embedding: List[float], top_k: int = 5,
               source_type_filter: Optional[str] = None,
               hitl_boost: float = 1.0) -> List[Dict[str, Any]]:
        """
        Cosine similarity search with optional HITL boost.
        
        Args:
            query_embedding: The query vector
            top_k: Number of results
            source_type_filter: Filter by source type (e.g., 'iway_api')
            hitl_boost: Multiplier for hitl_validated entries (e.g., 1.15)
        
        Returns:
            List of {chunk_text, metadata, similarity, source_type, source_id}
        """
        if not self.entries:
            return []

        if self._dirty:
            self._rebuild_index()

        query_vec = np.array(query_embedding)

        # Cosine similarity (embeddings are already normalized)
        similarities = self.embeddings @ query_vec

        # Apply HITL boost
        for i, entry in enumerate(self.entries):
            if entry["source_type"] == "hitl_validated":
                similarities[i] *= hitl_boost

        # Apply source type filter
        if source_type_filter:
            mask = np.array([e["source_type"] == source_type_filter for e in self.entries])
            similarities = np.where(mask, similarities, -1)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            if sim <= 0:
                continue
            entry = self.entries[idx]
            results.append({
                "chunk_text": entry["chunk_text"],
                "metadata": entry["metadata"],
                "similarity": round(sim, 4),
                "source_type": entry["source_type"],
                "source_id": entry["source_id"],
            })

        return results

    @property
    def count(self) -> int:
        return len(self.entries)

    def count_by_type(self) -> Dict[str, int]:
        """Count entries by source type."""
        counts = {}
        for e in self.entries:
            st = e["source_type"]
            counts[st] = counts.get(st, 0) + 1
        return counts


# --- Global store instance ---
knowledge_store = InMemoryVectorStore()


# ==============================================================
# HIGH-LEVEL RAG API
# ==============================================================

def sync_knowledge_from_api(kb_items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Sync knowledge base items from the I-Way mock API into the vector store.
    
    Args:
        kb_items: List of {"id", "question", "reponse", "cible", "tags"} dicts
    
    Returns:
        {"inserted": N, "updated": N, "total": N}
    """
    inserted = 0
    updated = 0

    # Build Q&A text for embedding
    texts = []
    for item in kb_items:
        text = f"Question: {item['question']}\nRéponse: {item['reponse']}"
        texts.append(text)

    # Batch embed
    embeddings = embed_texts(texts)

    # Upsert
    for item, text, embedding in zip(kb_items, texts, embeddings):
        result = knowledge_store.upsert(
            source_id=f"kb-{item['id']}",
            source_type="iway_api",
            chunk_text=text,
            embedding=embedding,
            metadata={
                "question": item["question"],
                "reponse": item["reponse"],
                "cible": item.get("cible", ""),
                "tags": item.get("tags", []),
                "original_id": item["id"],
            }
        )
        if result == "inserted":
            inserted += 1
        else:
            updated += 1

    logger.info(f"📚 Knowledge sync complete: {inserted} inserted, {updated} updated, {knowledge_store.count} total")
    return {"inserted": inserted, "updated": updated, "total": knowledge_store.count}


def add_hitl_knowledge(session_id: str, question: str, answer: str,
                       agent_matricule: str, agent_name: str,
                       tags: List[str] = None) -> Dict[str, Any]:
    """
    Add a HITL-validated Q&A pair to the knowledge store.
    Called when an agent resolves a session with 'save_to_knowledge' flag.
    
    Args:
        session_id: The session this came from
        question: The user's original question
        answer: The agent's validated answer
        agent_matricule: Who validated it
        agent_name: Agent display name
        tags: Optional topic tags
    
    Returns:
        {"status": "added", "source_id": "hitl-...", "store_count": N}
    """
    text = f"Question: {question}\nRéponse: {answer}"
    embedding = embed_text(text)

    source_id = f"hitl-{session_id}"
    knowledge_store.upsert(
        source_id=source_id,
        source_type="hitl_validated",
        chunk_text=text,
        embedding=embedding,
        metadata={
            "question": question,
            "reponse": answer,
            "session_id": session_id,
            "agent_matricule": agent_matricule,
            "agent_name": agent_name,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "tags": tags or [],
        }
    )

    logger.info(f"🧠 HITL knowledge added from session {session_id} by {agent_name}")
    return {
        "status": "added",
        "source_id": source_id,
        "store_count": knowledge_store.count,
    }


def retrieve_context(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """
    Main RAG retrieval function. Returns relevant knowledge chunks for a query.
    
    Uses weighted similarity with HITL boost (hitl_validated entries get 1.15x).
    
    Args:
        query: User's question
        top_k: Number of results (defaults to settings.RAG_TOP_K)
    
    Returns:
        List of {chunk_text, metadata, similarity, source_type, source_id}
    """
    if knowledge_store.count == 0:
        return []

    k = top_k or settings.RAG_TOP_K
    query_embedding = embed_text(query)

    results = knowledge_store.search(
        query_embedding=query_embedding,
        top_k=k,
        hitl_boost=settings.HITL_BOOST_FACTOR,
    )

    return results


def get_knowledge_stats() -> Dict[str, Any]:
    """Get current knowledge store statistics for the admin dashboard."""
    counts = knowledge_store.count_by_type()
    return {
        "total_entries": knowledge_store.count,
        "iway_api": counts.get("iway_api", 0),
        "hitl_validated": counts.get("hitl_validated", 0),
        "hitl_boost_factor": settings.HITL_BOOST_FACTOR,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
    }
