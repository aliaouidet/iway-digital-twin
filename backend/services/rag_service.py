"""
RAG Service — Embedding, PGVector storage, and similarity search.

Architecture (Phase 6):
  PRIMARY:   PGVector (PostgreSQL + pgvector extension) — persistent
  FALLBACK:  InMemoryVectorStore (numpy cosine similarity) — dev/no DB

Embedding models:
  - Default:  paraphrase-multilingual-MiniLM-L12-v2 (local, 384d)
  - Optional: Gemini embeddings via langchain-google-genai

IMPORTANT: All async code paths (FastAPI endpoints, WebSocket handlers)
must use the async_* variants to avoid blocking the event loop.
Sync variants are kept for Celery workers and startup code.
"""

import os
import asyncio
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
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


# --- Dedicated thread pool for CPU-bound embedding (avoids starving the default pool) ---
_embed_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed")


def embed_text(text: str) -> List[float]:
    """Embed a single text string (synchronous — for Celery workers and startup)."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch embed multiple texts (synchronous — for Celery workers and startup)."""
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return embeddings.tolist()


async def async_embed_text(text: str) -> List[float]:
    """Thread-pool-safe embedding for use inside async handlers.
    
    Runs the CPU-bound sentence-transformers encode() in a dedicated
    thread pool so it never blocks the FastAPI event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embed_pool, embed_text, text)


async def async_embed_texts(texts: List[str]) -> List[List[float]]:
    """Thread-pool-safe batch embedding for async contexts."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_embed_pool, embed_texts, texts)


# ==============================================================
# PGVECTOR STORE (Phase 6 — production persistence)
# ==============================================================

_pgvector_store = None
_pgvector_available = False


def _build_pgvector_connection_string() -> str:
    """Build a psycopg2-compatible connection string for PGVector.
    
    PGVector's LangChain integration uses psycopg2 (sync driver),
    NOT psycopg3 or asyncpg. We build from the same env vars
    used by the PostgresSaver checkpointer in Phase 4.
    """
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "iway")
    db_pass = os.getenv("DB_PASS", "iway_secret")
    db_name = os.getenv("DB_NAME", "iway_db")
    return f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def _get_pgvector_store():
    """Lazy-initialize the LangChain PGVector store.
    
    Uses the same iway_db as the LangGraph checkpointer.
    Creates the pgvector extension and collection table automatically.
    
    Returns None if PGVector is not available (falls back to in-memory).
    """
    global _pgvector_store, _pgvector_available
    
    if _pgvector_store is not None:
        return _pgvector_store
    
    if _pgvector_available is False and _pgvector_store is None:
        try:
            from langchain_community.vectorstores import PGVector
            from langchain_community.embeddings import HuggingFaceEmbeddings
            
            conn_str = _build_pgvector_connection_string()
            
            # Use the same embedding model as our manual embed functions
            embeddings = HuggingFaceEmbeddings(
                model_name=settings.EMBEDDING_MODEL,
                encode_kwargs={"normalize_embeddings": True},
            )
            
            _pgvector_store = PGVector(
                collection_name="iway_knowledge",
                connection_string=conn_str,
                embedding_function=embeddings,
                pre_delete_collection=False,  # Preserve existing data
            )
            _pgvector_available = True
            logger.info(f"🗄️ PGVector store initialized (collection: iway_knowledge)")
            
        except Exception as e:
            _pgvector_available = False
            logger.warning(f"⚠️ PGVector unavailable (using in-memory fallback): {e}")
    
    return _pgvector_store


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


# --- Global store instance (in-memory fallback) ---
knowledge_store = InMemoryVectorStore()


# ==============================================================
# HIGH-LEVEL RAG API
# ==============================================================

def sync_knowledge_from_api(kb_items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Sync knowledge base items into the vector store (PGVector or in-memory).
    
    Phase 6: Uses RecursiveCharacterTextSplitter to chunk long Q&A entries
    before embedding, then stores in PGVector for persistence. Falls back
    to in-memory store if PGVector is unavailable.
    
    Args:
        kb_items: List of {"id", "question", "reponse", "cible", "tags"} dicts
    
    Returns:
        {"inserted": N, "updated": N, "total": N, "store": "pgvector"|"in_memory"}
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    # -- Chunk the Q&A entries --
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ". ", ", ", " "],
    )
    
    documents = []
    metadatas = []
    source_ids = []
    
    for item in kb_items:
        # Build the full Q&A text
        full_text = f"Question: {item['question']}\nRéponse: {item['reponse']}"
        
        # Chunk it (most Q&A entries are <500 chars, so many will be 1 chunk)
        chunks = splitter.split_text(full_text)
        
        for chunk_idx, chunk in enumerate(chunks):
            documents.append(chunk)
            source_id = f"kb-{item['id']}-c{chunk_idx}"
            source_ids.append(source_id)
            metadatas.append({
                "question": item["question"],
                "reponse": item["reponse"],
                "cible": item.get("cible", ""),
                "tags": item.get("tags", []),
                "original_id": item["id"],
                "chunk_index": chunk_idx,
                "total_chunks": len(chunks),
                "source_type": "iway_api",
            })
    
    logger.info(f"📝 Chunked {len(kb_items)} Q&A entries into {len(documents)} chunks")
    
    # -- Try PGVector first (persistent) --
    pgvector = _get_pgvector_store()
    
    if pgvector is not None:
        try:
            from langchain_core.documents import Document
            
            # Build LangChain Document objects for PGVector
            lc_docs = []
            for text, meta, sid in zip(documents, metadatas, source_ids):
                meta_copy = {**meta, "source_id": sid}
                lc_docs.append(Document(page_content=text, metadata=meta_copy))
            
            # Idempotent: add_documents handles dedup via content hash
            pgvector.add_documents(lc_docs)
            
            logger.info(f"🗄️ PGVector sync complete: {len(lc_docs)} chunks stored")
            return {
                "inserted": len(lc_docs),
                "updated": 0,
                "total": len(lc_docs),
                "store": "pgvector",
                "chunks": len(documents),
            }
            
        except Exception as e:
            logger.warning(f"⚠️ PGVector sync failed, falling back to in-memory: {e}")
    
    # -- Fallback: in-memory store --
    inserted = 0
    updated = 0
    
    # Batch embed all chunks
    embeddings = embed_texts(documents)
    
    for text, embedding, meta, sid in zip(documents, embeddings, metadatas, source_ids):
        result = knowledge_store.upsert(
            source_id=sid,
            source_type="iway_api",
            chunk_text=text,
            embedding=embedding,
            metadata=meta,
        )
        if result == "inserted":
            inserted += 1
        else:
            updated += 1

    logger.info(f"📚 In-memory sync: {inserted} inserted, {updated} updated, {knowledge_store.count} total")
    return {
        "inserted": inserted,
        "updated": updated,
        "total": knowledge_store.count,
        "store": "in_memory",
        "chunks": len(documents),
    }


def add_hitl_knowledge(session_id: str, question: str, answer: str,
                       agent_matricule: str, agent_name: str,
                       tags: List[str] = None) -> Dict[str, Any]:
    """
    Add a HITL-validated Q&A pair to the knowledge store.
    Called when an agent resolves a session with 'save_to_knowledge' flag.
    
    Stores in PGVector (persistent) if available, otherwise in-memory.
    """
    text = f"Question: {question}\nRéponse: {answer}"
    source_id = f"hitl-{session_id}"
    
    metadata = {
        "question": question,
        "reponse": answer,
        "session_id": session_id,
        "agent_matricule": agent_matricule,
        "agent_name": agent_name,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
        "source_type": "hitl_validated",
        "source_id": source_id,
    }
    
    # Try PGVector first
    pgvector = _get_pgvector_store()
    if pgvector is not None:
        try:
            from langchain_core.documents import Document
            doc = Document(page_content=text, metadata=metadata)
            pgvector.add_documents([doc])
            logger.info(f"🧠 HITL knowledge added to PGVector from session {session_id} by {agent_name}")
            return {"status": "added", "source_id": source_id, "store": "pgvector"}
        except Exception as e:
            logger.warning(f"⚠️ PGVector HITL add failed: {e}")
    
    # Fallback: in-memory
    embedding = embed_text(text)
    knowledge_store.upsert(
        source_id=source_id,
        source_type="hitl_validated",
        chunk_text=text,
        embedding=embedding,
        metadata=metadata,
    )

    logger.info(f"🧠 HITL knowledge added (in-memory) from session {session_id} by {agent_name}")
    return {
        "status": "added",
        "source_id": source_id,
        "store_count": knowledge_store.count,
        "store": "in_memory",
    }


def retrieve_context(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """
    Main RAG retrieval function (synchronous — for Celery workers).
    
    Tries PGVector first (persistent), falls back to in-memory.
    Uses weighted similarity with HITL boost (hitl_validated entries get 1.15x).
    For async code paths, use async_retrieve_context() instead.
    """
    k = top_k or settings.RAG_TOP_K
    
    # Try PGVector first
    pgvector = _get_pgvector_store()
    if pgvector is not None:
        try:
            results = pgvector.similarity_search_with_score(query, k=k)
            formatted = []
            for doc, score in results:
                # PGVector returns distance; convert to similarity
                similarity = 1.0 - score if score <= 1.0 else max(0.0, 1.0 / (1.0 + score))
                formatted.append({
                    "chunk_text": doc.page_content,
                    "metadata": doc.metadata,
                    "similarity": round(similarity, 4),
                    "source_type": doc.metadata.get("source_type", "iway_api"),
                    "source_id": doc.metadata.get("source_id", "unknown"),
                })
            return formatted
        except Exception as e:
            logger.warning(f"⚠️ PGVector search failed, falling back to in-memory: {e}")
    
    # Fallback: in-memory
    if knowledge_store.count == 0:
        return []

    query_embedding = embed_text(query)
    results = knowledge_store.search(
        query_embedding=query_embedding,
        top_k=k,
        hitl_boost=settings.HITL_BOOST_FACTOR,
    )
    return results


async def async_retrieve_context(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """
    Async-safe RAG retrieval — won't block the event loop.
    
    Use this in all FastAPI endpoints and WebSocket handlers.
    The embedding computation runs in a dedicated thread pool.
    """
    k = top_k or settings.RAG_TOP_K
    
    # Try PGVector first (runs sync search in thread pool)
    pgvector = _get_pgvector_store()
    if pgvector is not None:
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                _embed_pool,
                lambda: pgvector.similarity_search_with_score(query, k=k)
            )
            formatted = []
            for doc, score in results:
                similarity = 1.0 - score if score <= 1.0 else max(0.0, 1.0 / (1.0 + score))
                formatted.append({
                    "chunk_text": doc.page_content,
                    "metadata": doc.metadata,
                    "similarity": round(similarity, 4),
                    "source_type": doc.metadata.get("source_type", "iway_api"),
                    "source_id": doc.metadata.get("source_id", "unknown"),
                })
            return formatted
        except Exception as e:
            logger.warning(f"⚠️ PGVector async search failed: {e}")
    
    # Fallback: in-memory
    if knowledge_store.count == 0:
        return []

    query_embedding = await async_embed_text(query)
    results = knowledge_store.search(
        query_embedding=query_embedding,
        top_k=k,
        hitl_boost=settings.HITL_BOOST_FACTOR,
    )
    return results


async def async_add_hitl_knowledge(
    session_id: str, question: str, answer: str,
    agent_matricule: str, agent_name: str,
    tags: List[str] = None,
) -> Dict[str, Any]:
    """
    Async-safe version of add_hitl_knowledge.
    Embeds and upserts a HITL-validated Q&A pair without blocking the event loop.
    """
    text = f"Question: {question}\nRéponse: {answer}"
    source_id = f"hitl-{session_id}"

    metadata = {
        "question": question,
        "reponse": answer,
        "session_id": session_id,
        "agent_matricule": agent_matricule,
        "agent_name": agent_name,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
        "source_type": "hitl_validated",
        "source_id": source_id,
    }

    # Try PGVector first
    pgvector = _get_pgvector_store()
    if pgvector is not None:
        try:
            from langchain_core.documents import Document
            doc = Document(page_content=text, metadata=metadata)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_embed_pool, lambda: pgvector.add_documents([doc]))
            logger.info(f"🧠 HITL knowledge added to PGVector from session {session_id}")
            return {"status": "added", "source_id": source_id, "store": "pgvector"}
        except Exception as e:
            logger.warning(f"⚠️ PGVector async HITL add failed: {e}")

    # Fallback: in-memory
    embedding = await async_embed_text(text)
    knowledge_store.upsert(
        source_id=source_id,
        source_type="hitl_validated",
        chunk_text=text,
        embedding=embedding,
        metadata=metadata,
    )

    logger.info(f"🧠 HITL knowledge added (in-memory) from session {session_id} by {agent_name}")
    return {
        "status": "added",
        "source_id": source_id,
        "store_count": knowledge_store.count,
        "store": "in_memory",
    }


def get_knowledge_stats() -> Dict[str, Any]:
    """Get current knowledge store statistics for the admin dashboard."""
    pgvector = _get_pgvector_store()
    
    if pgvector is not None:
        try:
            # PGVector collection stats
            from sqlalchemy import text, create_engine
            conn_str = _build_pgvector_connection_string()
            engine = create_engine(conn_str)
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = "
                    "(SELECT uuid FROM langchain_pg_collection WHERE name = 'iway_knowledge')"
                ))
                pg_count = result.scalar() or 0
            
            return {
                "total_entries": pg_count,
                "store": "pgvector",
                "collection": "iway_knowledge",
                "embedding_model": settings.EMBEDDING_MODEL,
                "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
                "hitl_boost_factor": settings.HITL_BOOST_FACTOR,
                # Also report in-memory count for comparison
                "in_memory_fallback_count": knowledge_store.count,
            }
        except Exception as e:
            logger.debug(f"PGVector stats query failed: {e}")
    
    # Fallback: in-memory stats
    counts = knowledge_store.count_by_type()
    return {
        "total_entries": knowledge_store.count,
        "store": "in_memory",
        "iway_api": counts.get("iway_api", 0),
        "hitl_validated": counts.get("hitl_validated", 0),
        "hitl_boost_factor": settings.HITL_BOOST_FACTOR,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
    }
