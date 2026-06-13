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


# ==============================================================
# Invariant 5 — wave 2 tools: provider search is PUBLIC (cacheable),
# factures/plafonds are PERSONAL (never cached, cache lookup bypassed)
# ==============================================================

class TestWave2CachePolicy:
    _BASE = {"source": "claims_graph", "confidence": 90, "degraded": False, "text": "ok"}

    def test_provider_search_response_IS_cacheable(self):
        """The headline wave-2 invariant: the conventioned-provider directory is
        public data — two users asking for 'un cardiologue à Sousse' may share
        a cached answer."""
        result = {**self._BASE, "intent": "provider_search", "tools_called": ["provider_search"]}
        assert is_cacheable_response(result) is True

    @pytest.mark.parametrize("tool", ["facture_lookup", "plafond_lookup"])
    def test_new_personal_tools_never_cached(self, tool):
        result = {**self._BASE, "intent": "personal_lookup", "tools_called": [tool]}
        assert is_cacheable_response(result) is False

    @pytest.mark.parametrize("q", [
        "mes factures",
        "où en est ma facture ?",
        "liste les factures",                 # possessive-less imperative
        "affiche la consommation de mon plafond",
        "mon plafond restant",
    ])
    def test_facture_plafond_queries_bypass_cache(self, q):
        assert is_personal_query(q) is True

    def test_provider_query_is_a_cacheable_lookup(self):
        assert is_personal_query("trouver un cardiologue conventionné à Sousse") is False


class TestWave2PiiShield:
    def test_plafond_records_shield_beneficiary_name(self):
        records = {"plafonds": [{
            "beneficiaire": "Fatma Tounsi", "lien": "conjoint",
            "montant_plafond": 3000.0, "montant_consomme": 410.0,
        }]}
        shielded, mapping = pseudonymize_records(records)
        blob = str(shielded)
        assert "Fatma Tounsi" not in blob
        assert "3000.0" in blob          # structural amounts stay readable
        assert "Fatma Tounsi" in mapping.values()

    def test_facture_records_carry_no_person_fields(self):
        # _map_facture plucks a fixed structural shape — nothing here should be
        # tokenized, the LLM needs all of it to reason about the invoice.
        records = {"factures": [{
            "num_facture": "FACT-2026-0231", "date": "2026-04-22",
            "montant": 1840.0, "statut": "En cours", "nature": "Facture bordereau",
        }]}
        shielded, mapping = pseudonymize_records(records)
        assert "FACT-2026-0231" in str(shielded)
        assert mapping == {}
