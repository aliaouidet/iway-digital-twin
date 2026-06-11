"""
Persistence Health — visibility into fire-and-forget DB writes.

Session/message persistence is intentionally fire-and-forget (a DB outage must
never break a live conversation), but failures used to vanish at debug level —
an hour-long outage lost an hour of history with zero signal. These counters
make the silent path observable on /health.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger("I-Way-Twin")

_failures: Dict[str, int] = {}
_consecutive: int = 0
_last_error: str = ""
_last_failure_at: str = ""

# After this many consecutive failures, escalate the log level so the outage
# shows up in `docker compose logs` without grepping for debug lines.
_ALERT_THRESHOLD = 5


def record_persist_failure(kind: str, error: Exception) -> None:
    global _consecutive, _last_error, _last_failure_at
    _failures[kind] = _failures.get(kind, 0) + 1
    _consecutive += 1
    _last_error = f"{kind}: {error}"
    _last_failure_at = datetime.now(timezone.utc).isoformat()
    if _consecutive == _ALERT_THRESHOLD:
        logger.error(
            f"🛑 {_ALERT_THRESHOLD} consecutive persistence failures — "
            f"conversation history is NOT being saved (last: {_last_error})"
        )
    else:
        logger.debug(f"Persistence failure ({kind}): {error}")


def record_persist_success() -> None:
    global _consecutive
    _consecutive = 0


def get_persistence_health() -> dict:
    return {
        "total_failures": sum(_failures.values()),
        "by_kind": dict(_failures),
        "consecutive_failures": _consecutive,
        "degraded": _consecutive >= _ALERT_THRESHOLD,
        "last_error": _last_error or None,
        "last_failure_at": _last_failure_at or None,
    }
