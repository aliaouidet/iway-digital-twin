"""
Referential lists — Redis-cached, non-personal ERP reference data.

The provider-search flow needs three slow/huge ERP referentials (villes &
gouvernorats ≈ 1.8 MB, secteurs d'activité, spécialités). They change rarely,
contain no personal data, and are shared across all users — so they are cached
in the shared Redis (TTL ``IWAY_REFERENTIAL_TTL_HOURS``) with an in-process
fallback when Redis is down, and a static gouvernorat list so filter parsing
works even fully offline (mock mode / tests).

Cache policy note: this is deliberately NOT the semantic cache — keys are exact
(`iway:ref:<name>`) and values are public directory data, so none of the
personal-data invariants in cache_policy.py apply here.
"""

import json
import logging
import time
from typing import Any, Callable, Optional

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

_KEY_PREFIX = "iway:ref:"

# Last-resort in-process copy (used when Redis is unavailable). {name: (expires_at, value)}
_local_cache: dict[str, tuple[float, Any]] = {}

# The 24 Tunisian gouvernorats — static fallback so provider-search filter
# extraction works offline (mock mode, tests, ERP unreachable).
GOUVERNORATS_TN = [
    "Ariana", "Béja", "Ben Arous", "Bizerte", "Gabès", "Gafsa", "Jendouba",
    "Kairouan", "Kasserine", "Kébili", "Le Kef", "Mahdia", "La Manouba",
    "Médenine", "Monastir", "Nabeul", "Sfax", "Sidi Bouzid", "Siliana",
    "Sousse", "Tataouine", "Tozeur", "Tunis", "Zaghouan",
]


def _ttl_seconds() -> int:
    return max(1, settings.IWAY_REFERENTIAL_TTL_HOURS) * 3600


async def _cached(name: str, loader: Callable) -> Optional[Any]:
    """Generic get-or-load: Redis → in-process → live SOAP loader.

    Returns None when the loader fails and nothing is cached (callers fall back
    to their static defaults).
    """
    key = _KEY_PREFIX + name

    # 1) shared Redis
    redis = None
    try:
        from backend.services.redis_client import get_redis
        redis = await get_redis()
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:  # Redis down → fall through to local/live
        logger.debug(f"referentials: redis read miss for {name}: {e}")

    # 2) in-process fallback
    entry = _local_cache.get(name)
    if entry and entry[0] > time.monotonic():
        return entry[1]

    # 3) live load (LAN-only — fails fast off-site)
    try:
        value = await loader()
    except Exception as e:
        logger.warning(f"⚠️ referentials: live load failed for {name}: {e}")
        return None

    _local_cache[name] = (time.monotonic() + _ttl_seconds(), value)
    if redis is not None:
        try:
            await redis.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=_ttl_seconds())
        except Exception as e:
            logger.debug(f"referentials: redis write failed for {name}: {e}")
    return value


async def get_villes_gouvernorats_cached() -> list[dict]:
    """[{"gouvernorat": str, "villes": [...]}, ...] — empty list when unavailable."""
    from backend.services import iway_soap_client as soap
    return await _cached("villes_gouvernorats", soap.get_villes_gouvernorats) or []


async def get_secteurs_cached() -> list[dict]:
    from backend.services import iway_soap_client as soap
    return await _cached("secteurs_activite", soap.get_secteurs_activite) or []


async def get_specialites_cached(id_secteur: int) -> list[dict]:
    from backend.services import iway_soap_client as soap

    async def _loader():
        return await soap.get_specialites_by_secteur(id_secteur)

    return await _cached(f"specialites_{id_secteur}", _loader) or []


async def known_gouvernorats() -> list[str]:
    """Gouvernorat names for filter extraction — live referential when available
    (real mode), else the static list. Always returns a non-empty list."""
    names: list[str] = []
    if settings.IWAY_USE_REAL_API:
        rows = await get_villes_gouvernorats_cached()
        names = [r.get("gouvernorat") for r in rows if isinstance(r, dict) and r.get("gouvernorat")]
    return names or list(GOUVERNORATS_TN)


def reset_local_cache() -> None:
    """Test helper."""
    _local_cache.clear()
