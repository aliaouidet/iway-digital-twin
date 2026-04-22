"""
Redis Client — Async connection pool singleton for I-Way Digital Twin.

Key naming convention (redis-development/data-key-naming rule):
    iway:cache:llm:{hash}             → LLM response cache
    iway:stats:queries:{YYYY-MM-DD}   → Daily query counter
    iway:stats:escalations:{YYYY-MM-DD} → Daily escalation counter
    iway:stats:cache_hits:{YYYY-MM-DD}  → Daily cache hit counter
    iway:stats:users:{YYYY-MM-DD}     → HyperLogLog unique users
    iway:stats:intents                → Sorted set of intent frequencies
    iway:stats:confidence             → List of recent confidence scores

Pool config (redis-development/conn-pooling rule):
    - Shared pool, max 20 connections
    - Decode responses to str
    - Graceful shutdown in FastAPI lifespan
"""

import logging
import redis.asyncio as aioredis
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get the shared async Redis client (lazy-init with connection pool)."""
    global _pool, _client
    if _client is not None:
        return _client

    settings = get_settings()
    _pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=20,
        decode_responses=True,
    )
    _client = aioredis.Redis(connection_pool=_pool)

    # Verify connectivity
    try:
        await _client.ping()
        logger.info("🔴 Redis connected (pool: 20 connections)")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e} — cache/analytics disabled")
        _client = None
        raise

    return _client


async def close_redis():
    """Gracefully close the Redis pool (call from FastAPI shutdown)."""
    global _pool, _client
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None
    logger.info("🔴 Redis pool closed")
