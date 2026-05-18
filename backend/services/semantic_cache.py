"""
Semantic Caching Layer using RedisVL.

Intersects exact matches and high-similarity semantic matches 
to short-circuit the LangGraph LLM pipeline, providing O(1) latency.
"""

import os
import logging
from typing import Optional

from redisvl.index import SearchIndex
from redisvl.schema import IndexSchema
from redisvl.query import VectorQuery

from backend.database.connection import get_embedding_model

logger = logging.getLogger("I-Way-Twin")

# Define RedisVL Schema
schema = IndexSchema.from_dict({
    "index": {
        "name": "iway_semantic_cache",
        "prefix": "cache:",
        "storage_type": "hash"
    },
    "fields": [
        {"name": "query", "type": "text"},
        {"name": "response", "type": "text"},
        {
            "name": "query_vector",
            "type": "vector",
            "attrs": {
                "dims": 384,  # all-MiniLM-L6-v2 dimension
                "distance_metric": "cosine",
                "algorithm": "flat",
                "datatype": "float32"
            }
        }
    ]
})

_index: Optional[SearchIndex] = None

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
        # Generate embedding for the query
        embedder = get_embedding_model()
        vector = await embedder.aembed_query(query)

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
                return best_match["response"]
                
    except Exception as e:
        logger.warning(f"Semantic Cache search failed: {e}")
        
    return None

async def store_semantic_cache(query: str, response: str):
    """
    Store the LLM response in the semantic cache.
    """
    index = get_cache_index()
    if not index:
        return

    try:
        embedder = get_embedding_model()
        vector = await embedder.aembed_query(query)
        
        data = {
            "query": query,
            "response": response,
            "query_vector": vector
        }
        
        index.load([data])
        logger.debug(f"Stored query in Semantic Cache: '{query[:30]}...'")
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
        embedder = get_embedding_model()
        vector = await embedder.aembed_query(query)
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
