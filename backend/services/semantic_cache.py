"""
Semantic Caching Layer using RedisVL.

Intersects exact matches and high-similarity semantic matches 
to short-circuit the LangGraph LLM pipeline, providing O(1) latency.
"""

import os
import re
import logging
from typing import Optional

from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema
from redisvl.query import VectorQuery

from backend.config import get_settings
from backend.services.rag_service import embed_text

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# The index name embeds the embedding-model slug: swapping the model creates a
# FRESH index instead of mixing incompatible vector spaces (old entries simply
# expire via TTL). Dims come from settings — they must match the model.
_MODEL_SLUG = re.sub(r"[^a-z0-9]+", "_", settings.EMBEDDING_MODEL.lower()).strip("_")
_INDEX_NAME = f"iway_semantic_cache_v5_{_MODEL_SLUG}"

# Define RedisVL Schema
schema = IndexSchema.from_dict({
    "index": {
        "name": _INDEX_NAME,
        "prefix": f"{_INDEX_NAME}:",
        "storage_type": "hash"
    },
    "fields": [
        {"name": "query", "type": "text"},
        {"name": "response", "type": "text"},
        {
            "name": "query_vector",
            "type": "vector",
            "attrs": {
                "dims": settings.EMBEDDING_DIMENSIONS,
                "distance_metric": "cosine",
                # HNSW: O(log n) lookups — the old "flat" algorithm full-scanned
                # every cached vector on the hottest path of every message.
                "algorithm": "hnsw",
                "datatype": "float32"
            }
        }
    ]
})

_index: Optional[SearchIndex] = None

# Cache policy (what is safe to cache) lives in cache_policy.py — re-exported here
# for convenience. SECURITY: per-user responses are never cacheable. See that module.
from backend.services.cache_policy import is_cacheable_response  # noqa: E402,F401

def get_cache_index() -> Optional[SearchIndex]:
    """Lazy initialize the RedisVL index."""
    global _index
    if _index is not None:
        return _index

    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _index = SearchIndex(schema, redis_url=redis_url)
        _index.create(overwrite=False)
        logger.info("Semantic Cache index initialized in Redis Stack.")
        return _index
    except Exception as e:
        logger.warning(f"Failed to initialize Semantic Cache (is Redis Stack running?): {e}")
        return None

async def check_semantic_cache(query: str, similarity_threshold: float = 0.95) -> Optional[str]:
    """
    Check if a semantically similar query was asked recently.
    """
    index = get_cache_index()
    if not index:
        return None

    try:
        # Embed in a worker thread — sentence-transformers is CPU-bound and
        # would otherwise block the event loop (stalling ALL requests) for the
        # duration of the encode (seconds, on a cold model).
        import anyio
        vector = await anyio.to_thread.run_sync(embed_text, query)

        # Build vector query
        v_query = VectorQuery(
            vector=vector,
            vector_field_name="query_vector",
            return_fields=["query", "response"],
            num_results=1
        )

        results = index.query(v_query)

        if results:
            best_match = results[0]
            distance = float(best_match.get("vector_distance", 1.0))
            similarity = 1.0 - distance

            if similarity >= similarity_threshold:
                logger.info(f"⚡ Semantic Cache Hit! Similarity: {similarity:.3f} for query: '{query[:30]}...'")
                from backend.services.metrics import CACHE_LOOKUPS
                CACHE_LOOKUPS.labels(result="hit").inc()
                return best_match["response"]

    except Exception as e:
        logger.warning(f"Semantic Cache search failed: {e}")

    from backend.services.metrics import CACHE_LOOKUPS
    CACHE_LOOKUPS.labels(result="miss").inc()
    return None

async def store_semantic_cache(query: str, response: str):
    """
    Store the LLM response in the semantic cache.
    """
    index = get_cache_index()
    if not index:
        return

    try:
        import anyio
        vector = await anyio.to_thread.run_sync(embed_text, query)

        import numpy as np
        vector_bytes = np.array(vector, dtype=np.float32).tobytes()
        
        data = {
            "query": query,
            "response": response,
            "query_vector": vector_bytes
        }

        keys = index.load([data])
        # TTL: cached answers expire instead of living until LRU eviction —
        # bounds staleness (policy changes) AND keeps the index small.
        ttl_seconds = settings.SEMANTIC_CACHE_TTL_HOURS * 3600
        for key in keys or []:
            index.client.expire(key, ttl_seconds)
        logger.debug(f"Stored query in Semantic Cache (TTL {settings.SEMANTIC_CACHE_TTL_HOURS}h): '{query[:30]}...'")
    except Exception as e:
        logger.warning(f"Failed to store in Semantic Cache: {e}")

async def invalidate_semantic_cache(query: str):
    """
    Remove a cached response for an exact query match.
    Used when HITL corrects an answer.
    """
    index = get_cache_index()
    if not index:
        return
        
    try:
        from redisvl.query import FilterQuery
        from redisvl.query.filter import Tag
        
        # We need to find the exact query and delete it.
        # Since we didn't tag the query, we can just do a vector search with score 1.0 and delete the key.
        vector = embed_text(query)
        v_query = VectorQuery(
            vector=vector,
            vector_field_name="query_vector",
            return_fields=["id"],
            num_results=1
        )
        results = index.query(v_query)
        if results:
            best_match = results[0]
            distance = float(best_match.get("vector_distance", 1.0))
            similarity = 1.0 - distance
            if similarity > 0.99:  # Practically identical
                key = best_match.get("id")
                if key:
                    index.client.delete(key)
                    logger.info(f"🗑️ Semantic Cache invalidated for exact query.")
    except Exception as e:
        logger.debug(f"Semantic cache invalidation skipped: {e}")
