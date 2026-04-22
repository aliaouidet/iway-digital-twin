"""
Analytics — Real-time counters using Redis atomic operations.

Data structures (redis-development/data-choose-structure + data-incr rules):
  - String counters:  INCR for queries, escalations, cache_hits
  - HyperLogLog:      PFADD for unique user count (~12 bytes)
  - Sorted Set:       ZINCRBY for intent frequency ranking
  - List:             LPUSH/LTRIM for rolling confidence window

All daily keys auto-expire after 48 hours (ram-ttl rule).
"""

import logging
from datetime import date

logger = logging.getLogger("I-Way-Twin")

STATS_PREFIX = "iway:stats"
DAILY_TTL = 48 * 3600  # 48 hours — keeps yesterday for comparison


def _today() -> str:
    """Date key for daily counters."""
    return date.today().isoformat()


async def record_query(
    matricule: str = None,
    intent: str = None,
    confidence: float = None,
    cache_hit: bool = False,
):
    """Record a single query event across multiple Redis counters.

    Fire-and-forget — errors are silently logged, never block the response.
    """
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        day = _today()

        # Pipeline for atomicity + fewer round-trips (conn-pipelining rule)
        pipe = redis.pipeline(transaction=False)

        # Daily query counter (INCR — atomic, O(1))
        qkey = f"{STATS_PREFIX}:queries:{day}"
        pipe.incr(qkey)
        pipe.expire(qkey, DAILY_TTL)

        # Cache hit counter
        if cache_hit:
            chkey = f"{STATS_PREFIX}:cache_hits:{day}"
            pipe.incr(chkey)
            pipe.expire(chkey, DAILY_TTL)

        # Unique users (HyperLogLog — ~12 bytes regardless of cardinality)
        if matricule:
            ukey = f"{STATS_PREFIX}:users:{day}"
            pipe.pfadd(ukey, matricule)
            pipe.expire(ukey, DAILY_TTL)

        # Intent frequency (Sorted Set — ZINCRBY is O(log N))
        if intent:
            pipe.zincrby(f"{STATS_PREFIX}:intents", 1, intent)

        # Rolling confidence window (last 100 values)
        if confidence is not None:
            ckey = f"{STATS_PREFIX}:confidence"
            pipe.lpush(ckey, str(round(confidence, 2)))
            pipe.ltrim(ckey, 0, 99)  # Keep only last 100

        await pipe.execute()
    except Exception as e:
        logger.debug(f"Analytics record skipped: {e}")


async def record_escalation():
    """Increment daily escalation counter."""
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        day = _today()
        ekey = f"{STATS_PREFIX}:escalations:{day}"
        await redis.incr(ekey)
        await redis.expire(ekey, DAILY_TTL)
    except Exception as e:
        logger.debug(f"Escalation counter skipped: {e}")


async def get_realtime_stats() -> dict:
    """Read all analytics counters from Redis (O(1) per counter).

    Returns a dict ready for the dashboard API.
    """
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        day = _today()

        pipe = redis.pipeline(transaction=False)
        pipe.get(f"{STATS_PREFIX}:queries:{day}")
        pipe.get(f"{STATS_PREFIX}:escalations:{day}")
        pipe.get(f"{STATS_PREFIX}:cache_hits:{day}")
        pipe.pfcount(f"{STATS_PREFIX}:users:{day}")
        pipe.zrevrange(f"{STATS_PREFIX}:intents", 0, 9, withscores=True)
        pipe.lrange(f"{STATS_PREFIX}:confidence", 0, 99)

        results = await pipe.execute()

        queries_today = int(results[0] or 0)
        escalations_today = int(results[1] or 0)
        cache_hits_today = int(results[2] or 0)
        unique_users = int(results[3] or 0)
        top_intents = [{"intent": i, "count": int(s)} for i, s in (results[4] or [])]
        confidence_values = [float(v) for v in (results[5] or [])]
        avg_confidence = (
            round(sum(confidence_values) / len(confidence_values), 2)
            if confidence_values
            else None
        )

        cache_hit_rate = (
            round(cache_hits_today / queries_today * 100, 1)
            if queries_today > 0
            else 0.0
        )

        return {
            "queries_today": queries_today,
            "escalations_today": escalations_today,
            "cache_hits_today": cache_hits_today,
            "cache_hit_rate_pct": cache_hit_rate,
            "unique_users_today": unique_users,
            "avg_confidence": avg_confidence,
            "top_intents": top_intents,
            "date": day,
        }
    except Exception as e:
        logger.debug(f"Analytics read failed: {e}")
        return {"error": str(e), "date": _today()}
