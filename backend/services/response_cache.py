"""
Response Cache — Hash-based LLM response cache using Redis.

Strategy (redis-development/semantic-cache-best-practices):
  - Hash-based exact match (normalize → sha256 → lookup)
  - Only caches responses with confidence ≥ 70 (no uncertain answers)
  - TTL: 1 hour (redis-development/ram-ttl rule)
  - Invalidation: delete by query hash on HITL correction

Key format (redis-development/data-key-naming rule):
  iway:cache:llm:{sha256_hex_prefix}
"""

import json
import hashlib
import logging
import unicodedata
from datetime import datetime

logger = logging.getLogger("I-Way-Twin")

# Cache configuration
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_MIN_CONFIDENCE = 70  # Only cache high-confidence responses
CACHE_KEY_PREFIX = "iway:cache:llm"


def _normalize_query(query: str) -> str:
    """Normalize query for cache key generation.

    - Lowercase
    - Strip whitespace
    - Remove accents (é → e, à → a)
    - Collapse multiple spaces
    """
    text = query.lower().strip()
    # Remove accents
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Collapse whitespace
    text = " ".join(text.split())
    return text


def _cache_key(query: str) -> str:
    """Generate Redis cache key from normalized query."""
    normalized = _normalize_query(query)
    query_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"{CACHE_KEY_PREFIX}:{query_hash}"


async def get_cached_response(query: str) -> dict | None:
    """Check Redis for a cached LLM response.

    Returns the cached response dict or None on miss/error.
    """
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        key = _cache_key(query)
        cached = await redis.get(key)
        if cached:
            data = json.loads(cached)
            logger.debug(f"✅ Cache HIT: {key}")
            return data
        return None
    except Exception as e:
        logger.debug(f"Cache lookup skipped: {e}")
        return None


async def set_cached_response(query: str, response: dict):
    """Store an LLM response in Redis cache.

    Only caches if confidence ≥ CACHE_MIN_CONFIDENCE.
    TTL: 1 hour (auto-expires, no cleanup needed).
    """
    confidence = response.get("confidence", 0)
    if confidence < CACHE_MIN_CONFIDENCE:
        return  # Don't cache uncertain answers

    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        key = _cache_key(query)
        payload = {
            "text": response.get("text", ""),
            "confidence": confidence,
            "source": "cache",
            "original_source": response.get("source", "unknown"),
            "cached_at": datetime.utcnow().isoformat(),
        }
        await redis.set(key, json.dumps(payload, ensure_ascii=False), ex=CACHE_TTL_SECONDS)
        logger.debug(f"📦 Cache SET: {key} (TTL={CACHE_TTL_SECONDS}s)")
    except Exception as e:
        logger.debug(f"Cache store skipped: {e}")


async def invalidate_cache(query: str):
    """Remove a cached response (used when HITL corrects an answer)."""
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        key = _cache_key(query)
        deleted = await redis.delete(key)
        if deleted:
            logger.info(f"🗑️ Cache invalidated: {key}")
    except Exception as e:
        logger.debug(f"Cache invalidation skipped: {e}")
