"""
KB Feedback — the data-flywheel signal layer for HITL knowledge entries.

Turns the static 1.15× HITL boost into a *feedback-weighted* one: entries that
demonstrably help (positive CSAT on sessions where they were retrieved) rise;
entries that correlate with thumbs-down sink and get flagged for review.

Counters live in Redis (fail-open — a Redis outage degrades to the neutral base
boost and silently drops recording, never blocking retrieval or chat):
  - ``iway:kb:{source_id}``  hash {retrieved, helpful, unhelpful}
  - ``iway:kb:sess:{session_id}``  set of source_ids retrieved in that session
    (TTL-bounded), so a later CSAT rating can be attributed back to the entries
    that actually fed the answer.
"""

import logging
from typing import Dict, List

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

_KB_PREFIX = "iway:kb"
_SESS_TTL = 24 * 3600


def _entry_key(source_id: str) -> str:
    return f"{_KB_PREFIX}:{source_id}"


def _sess_key(session_id: str) -> str:
    return f"{_KB_PREFIX}:sess:{session_id}"


def helpfulness_to_boost(helpful: int, unhelpful: int) -> float:
    """Map a helpful/unhelpful tally to a retrieval multiplier.

    No feedback → neutral (== HITL_BOOST_FACTOR, the old static value), so
    behaviour is unchanged until signal accrues. All-helpful pushes toward
    HITL_BOOST_MAX; all-unhelpful pulls below the base.
    """
    total = helpful + unhelpful
    rate = (helpful / total) if total else 0.5
    base = settings.HITL_BOOST_FACTOR - 1.0
    boost = 1.0 + base * (0.5 + rate)            # rate 0.5 → exactly HITL_BOOST_FACTOR
    return max(1.0, min(settings.HITL_BOOST_MAX, boost))


async def get_boost_async(source_id: str) -> float:
    """Feedback-weighted boost for one HITL entry (neutral on any failure)."""
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        data = await redis.hgetall(_entry_key(source_id)) or {}
        helpful = int(data.get("helpful", 0) or 0)
        unhelpful = int(data.get("unhelpful", 0) or 0)
        return helpfulness_to_boost(helpful, unhelpful)
    except Exception as e:
        logger.debug(f"kb_feedback boost neutral ({e})")
        return settings.HITL_BOOST_FACTOR


async def record_session_retrieval(session_id: str, source_ids: List[str]) -> None:
    """Count a retrieval for each HITL entry + remember them for outcome attribution."""
    ids = [s for s in (source_ids or []) if s and str(s).startswith("hitl-")]
    if not ids:
        return
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        pipe = redis.pipeline(transaction=False)
        for sid in ids:
            pipe.hincrby(_entry_key(sid), "retrieved", 1)
        pipe.sadd(_sess_key(session_id), *ids)
        pipe.expire(_sess_key(session_id), _SESS_TTL)
        await pipe.execute()
    except Exception as e:
        logger.debug(f"kb_feedback retrieval record skipped ({e})")


async def record_session_outcome(session_id: str, helpful: bool) -> None:
    """Attribute a session-level signal (CSAT thumb) to the entries it retrieved."""
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        ids = await redis.smembers(_sess_key(session_id))
        if not ids:
            return
        field = "helpful" if helpful else "unhelpful"
        pipe = redis.pipeline(transaction=False)
        for sid in ids:
            pipe.hincrby(_entry_key(sid), field, 1)
        await pipe.execute()
    except Exception as e:
        logger.debug(f"kb_feedback outcome record skipped ({e})")


async def get_stats_async(source_id: str) -> Dict[str, float]:
    """Per-entry {retrieved, helpful, unhelpful, helpfulness, boost} for the curation UI."""
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        data = await redis.hgetall(_entry_key(source_id)) or {}
        retrieved = int(data.get("retrieved", 0) or 0)
        helpful = int(data.get("helpful", 0) or 0)
        unhelpful = int(data.get("unhelpful", 0) or 0)
        total = helpful + unhelpful
        return {
            "retrieved": retrieved,
            "helpful": helpful,
            "unhelpful": unhelpful,
            "helpfulness": round(helpful / total, 2) if total else None,
            "boost": round(helpfulness_to_boost(helpful, unhelpful), 3),
        }
    except Exception:
        return {"retrieved": 0, "helpful": 0, "unhelpful": 0, "helpfulness": None,
                "boost": settings.HITL_BOOST_FACTOR}
