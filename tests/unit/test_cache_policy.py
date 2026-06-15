"""Unit tests for the shared-cache safety policy (security invariant #1)."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from backend.services.cache_policy import (
    is_cacheable_response, is_personal_query, is_escalation_query, _PERSONAL_TOOLS,
)

_BASE = {"confidence": 95, "degraded": False, "source": "claims_graph", "tools_called": []}


def test_personal_tools_cover_every_personal_lookup():
    for t in ("dossier_lookup", "beneficiary_lookup", "reclamation_lookup",
              "dossier_detail_lookup", "facture_lookup", "plafond_lookup"):
        assert t in _PERSONAL_TOOLS


def test_generic_high_confidence_answer_is_cacheable():
    assert is_cacheable_response(dict(_BASE)) is True


def test_personal_tool_blocks_caching():
    assert is_cacheable_response({**_BASE, "tools_called": ["beneficiary_lookup"]}) is False


def test_personal_intent_blocks_caching():
    assert is_cacheable_response({**_BASE, "intent": "personal_lookup"}) is False
    assert is_cacheable_response({**_BASE, "intent": "claim_action"}) is False


def test_low_confidence_degraded_untrusted_and_cachehit_block():
    assert is_cacheable_response({**_BASE, "confidence": 50}) is False
    assert is_cacheable_response({**_BASE, "degraded": True}) is False
    assert is_cacheable_response({**_BASE, "source": "rag_fallback"}) is False
    assert is_cacheable_response(dict(_BASE), cache_hit=True) is False
    assert is_cacheable_response(None) is False


def test_personal_queries_bypass_cache_lookup():
    assert is_personal_query("mes remboursements ?")
    assert is_personal_query("affiche mes dossiers")
    assert is_personal_query("liste les bénéficiaires")


def test_generic_query_does_not_bypass():
    assert is_personal_query("Comment fonctionne le remboursement ?") is False
    assert is_personal_query("") is False


def test_escalation_responses_are_never_cacheable():
    # An escalation/handoff response must not be cached (replaying it would skip
    # the actual queueing) even though it's high-confidence + from claims_graph.
    assert is_cacheable_response({**_BASE, "claim_status": "pending_human"}) is False
    assert is_cacheable_response({**_BASE, "intent": "escalation"}) is False


def test_escalation_queries_bypass_cache_lookup():
    for q in ("Parler à un agent", "je veux parler à un humain",
              "talk to a human", "speak to an agent", "escalate to human",
              "un agent humain s'il vous plaît"):
        assert is_escalation_query(q), q


def test_non_escalation_queries_not_flagged():
    assert is_escalation_query("Quel est le plafond dentaire ?") is False
    assert is_escalation_query("") is False
