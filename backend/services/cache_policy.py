"""
Cache policy — decides WHAT may enter the shared semantic cache.

Kept separate from semantic_cache.py (the Redis/RedisVL mechanism) so the
policy is pure, dependency-free, and unit-testable without a running cache.

SECURITY: the semantic cache is shared across all users and keyed by query text
only (no per-user scope). Any response built from per-user data (dossiers,
bénéficiaires, remboursements, réclamations, claim details) must NEVER be cached,
or User B could receive User A's data on a semantically similar query.
"""

import re
from typing import Optional

# Tools whose presence means the response contains PER-USER data.
# NOTE: "provider_search" is DELIBERATELY absent — the conventioned-provider
# directory is public data shared by all users, so those answers may be cached.
_PERSONAL_TOOLS = {
    "dossier_lookup", "beneficiary_lookup",
    "reclamation_lookup", "dossier_detail_lookup",
    "facture_lookup", "plafond_lookup",
}

# Response sources trusted enough to cache.
_CACHEABLE_SOURCES = {"claims_graph", "iway_api", "hitl_validated"}


def is_cacheable_response(ai_result: Optional[dict], cache_hit: bool = False) -> bool:
    """Whether a chat response may be stored in the shared semantic cache.

    Cacheable only when: not already a cache hit, high confidence (>=70),
    not degraded, from a trusted source, AND user-agnostic (no personal/claim
    data). This is the guard that prevents cross-user PII leakage.
    """
    if cache_hit or not ai_result:
        return False
    if ai_result.get("confidence", 0) < 70:
        return False
    if ai_result.get("degraded", False):
        return False
    if ai_result.get("source", "") not in _CACHEABLE_SOURCES:
        return False
    intent = (ai_result.get("intent") or "").lower()
    tools = ai_result.get("tools_called") or []
    if any(t in _PERSONAL_TOOLS for t in tools) or "personal_lookup" in intent or "claim_action" in intent:
        return False
    # Escalation/handoff responses must NEVER be cached: replaying the handoff
    # TEXT on a later cache hit would skip the actual queueing (no ticket, no
    # agent broadcast) — the user would *think* they reached an agent. See the
    # escalation intercept in chat_service.handle_chat_websocket.
    if ai_result.get("claim_status") == "pending_human" or "escalation" in intent:
        return False
    return True


# ── Cache LOOKUP gate ─────────────────────────────────────────
# French possessives signalling the user asks about THEIR OWN data.
_PERSONAL_QUERY_RE = re.compile(r"\b(mes|mon|ma|miens?|miennes?)\b", re.IGNORECASE)

# Possessive-less imperatives that still target the user's own records
# ("affiche les remboursements", "liste les bénéficiaires").
_PERSONAL_IMPERATIVE_RE = re.compile(
    r"\b(affiche[rz]?|liste[rz]?|montre[rz]?|consulte[rz]?|voir)\b"
    r".{0,40}?\b(dossiers?|remboursements?|b[ée]n[ée]ficiaires?|r[ée]clamations?|contrats?|historique|factures?|plafonds?|consommation)",
    re.IGNORECASE | re.DOTALL,
)


def is_personal_query(text: str) -> bool:
    """Whether a query is about the user's OWN data — the cache must be bypassed.

    A cached generic knowledge answer must never shadow a real per-user lookup
    (e.g. "mes remboursements ?" hitting a cached "comment fonctionne le
    remboursement" answer). Deliberately biased toward True: wrongly skipping
    the cache costs a few hundred ms; wrongly serving a cached answer to a
    personal query is a correctness bug. Possessive pronouns or a dossier-style
    reference number both trigger the bypass.
    """
    if not text:
        return False
    if _PERSONAL_QUERY_RE.search(text) or _PERSONAL_IMPERATIVE_RE.search(text):
        return True
    from backend.domain.graph.routing import extract_dossier_number
    return extract_dossier_number(text) is not None


# Phrases asking to reach a human/agent. Biased toward True like is_personal_query:
# a false bypass just re-runs the graph (a little latency); a false cache HIT
# would silently drop the escalation (no ticket / no queue) — a correctness bug.
_ESCALATION_QUERY_RE = re.compile(
    r"agent\s+humain|conseiller|"
    r"\b(un|une|d['e]?\s*)?(agent|humain)\b|"
    r"parler\s+(?:à|a|avec)\s+(?:un|une|quelqu|qqn|qq1)|"
    r"(?:talk|speak|chat)\s+to\s+(?:a\s+|an\s+)?(?:human|agent|someone|advisor|person|rep)|"
    r"human\s+agent|real\s+person|"
    r"escalat|escalad",
    re.IGNORECASE,
)


def is_escalation_query(text: str) -> bool:
    """Whether the user is asking to reach a human — the cache must be bypassed
    so the request actually escalates (queue + ticket) via the graph each time,
    never a replayed cached handoff message."""
    return bool(text) and bool(_ESCALATION_QUERY_RE.search(text))
