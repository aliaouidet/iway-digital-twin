"""
Offline unit tests for the SECURITY INVARIANTS (CLAUDE.md §Security invariants).

These four modules guard the system's trust boundaries; until now they were
protected only by convention and review. Run without the Docker stack:

    GOOGLE_API_KEY=offline ./venv/Scripts/python.exe -m pytest tests/test_invariants.py -v
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "offline")

import pytest


# ==============================================================
# Invariant 1 — cache policy: personal data must never be cached
# ==============================================================

from backend.services.cache_policy import is_cacheable_response, is_personal_query


class TestCachePolicy:
    def test_personal_tool_response_not_cacheable(self):
        assert is_cacheable_response({"tools_called": ["dossier_lookup"], "confidence": 95}) is False

    def test_general_graph_response_cacheable(self):
        assert is_cacheable_response({"tools_called": [], "source": "claims_graph", "confidence": 90, "text": "ok"}) is True

    def test_untrusted_source_not_cacheable(self):
        # Source allowlist: anything outside claims_graph/iway_api/hitl_validated stays out
        assert is_cacheable_response({"tools_called": [], "source": "rag", "confidence": 90, "text": "ok"}) is False

    def test_cache_hit_never_recached(self):
        assert is_cacheable_response({"tools_called": [], "text": "ok"}, cache_hit=True) is False

    def test_none_result_not_cacheable(self):
        assert is_cacheable_response(None) is False

    @pytest.mark.parametrize("q", [
        "mes remboursements",
        "où en est ma réclamation ?",
        "mon dossier DOS-2026-0042",
        "donne-moi mes bénéficiaires",
    ])
    def test_personal_queries_bypass_cache(self, q):
        assert is_personal_query(q) is True

    @pytest.mark.parametrize("q", [
        "quels sont les délais de remboursement ?",
        "comment déclarer une maladie chronique ?",
        "quels documents pour l'optique ?",
    ])
    def test_general_queries_are_cacheable_lookups(self, q):
        assert is_personal_query(q) is False


# ==============================================================
# Invariant 2 — PII shield: pseudonymize before LLM, restore after
# ==============================================================

from backend.services.pii_guard import pseudonymize_records, restore_pii


class TestPiiGuard:
    def test_roundtrip_restores_values(self):
        records = {"beneficiaires": [{"nom": "Ahmed Tounsi", "lien": "titulaire"}]}
        shielded, mapping = pseudonymize_records(records)
        # The real name must NOT appear in what would reach the external LLM
        assert "Ahmed Tounsi" not in str(shielded)
        # And the LLM's draft (containing the token) must be restorable
        token = next(iter(mapping.keys()))
        assert restore_pii(f"Le titulaire est {token}.", mapping) == "Le titulaire est Ahmed Tounsi."

    def test_non_pii_keys_untouched(self):
        records = {"dossiers": [{"id": "DOS-1", "montant": 180.0, "status": "rembourse"}]}
        shielded, _ = pseudonymize_records(records)
        assert "DOS-1" in str(shielded) and "180.0" in str(shielded)

    def test_empty_mapping_is_noop_on_restore(self):
        assert restore_pii("texte sans tokens", {}) == "texte sans tokens"


# ==============================================================
# Invariant 3 — escalation gate: réclamation filed ONLY on explicit intent
# ==============================================================

from backend.domain.graph.nodes.escalation import wants_formal_complaint, _handoff_message


class TestEscalationGate:
    @pytest.mark.parametrize("msg", [
        "je veux déposer une réclamation",
        "Je souhaite porter plainte",
        "comment faire une réclamation contre ce retard",
    ])
    def test_explicit_filing_intent_detected(self, msg):
        assert wants_formal_complaint(msg) is True

    @pytest.mark.parametrize("msg", [
        "je suis très énervé, c'est inadmissible",          # anger ≠ filing
        "je veux parler à un agent",                          # human request ≠ filing
        "où en est ma réclamation REC-2026-001 ?",            # status check ≠ filing
        "",
        None,
    ])
    def test_no_write_without_explicit_intent(self, msg):
        assert wants_formal_complaint(msg) is False

    def test_handoff_message_empathy_only_when_frustrated(self):
        assert "frustration" in _handoff_message("c'est inadmissible je suis frustré")
        assert "frustration" not in _handoff_message("je veux annuler ma demande")  # 'annuler' must not trigger

    def test_handoff_message_never_invents_queue_position(self):
        # The fake "position dans la file : 1" must never come back
        assert "position" not in _handoff_message("je veux un agent").lower()


# ==============================================================
# Invariant 4 — routing: status checks are lookups, dossier ids parse
# ==============================================================

from backend.domain.graph.routing import extract_dossier_number


class TestRouting:
    @pytest.mark.parametrize("msg,expected", [
        ("détail du dossier DOS-2026-0042", "DOS-2026-0042"),
        ("dossier 123456", "123456"),
        ("rien à extraire ici", None),
    ])
    def test_extract_dossier_number(self, msg, expected):
        assert extract_dossier_number(msg) == expected
