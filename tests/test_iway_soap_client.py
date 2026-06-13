"""
Offline tests for the real I-Way SOAP integration.

Three layers, all runnable WITHOUT the company LAN:
  1. WSDL parsing  — build each zeep client from the bundled local WSDLs and assert
                     the target operations exist (proves off-network build works).
  2. Mappers       — feed representative serialized DTO dicts and assert the compact
                     system_records shapes. (No zeep needed.)
  3. Node fallback — when a SOAP call raises, the graph lookup nodes degrade to mock.

Run:  pytest tests/test_iway_soap_client.py -v
"""

import os
import asyncio

# The graph nodes (imported by the fallback tests) build the Gemini LLM at import
# time, which requires *some* API key to construct. Provide a dummy — it is never
# called in these offline tests.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-offline")

import pytest

from backend.services import iway_soap_client as soap

WSDL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Webservices")


# ──────────────────────────────────────────────────────────────
# 1. WSDL parsing (offline) — requires zeep + the bundled WSDLs
# ──────────────────────────────────────────────────────────────
TARGET_OPS = {
    "contrat": ["getContratAdherentByMatricule", "getListeBeneficiairesByMatricule",
                "getListPlafondBeneficiairesByMatricule"],
    "remboursement": ["getListRemboursementByMatricule", "getDossierRemboursementByNumDossier", "createBsDigital"],
    "reclamation": ["getListReclamationByMatricule", "createReclamation"],
    "contrat_ps": ["getContratPsByMatriculeFiscal", "getContratPsByIdTiers"],
    "prestataire_search": ["searchPsWithConvTP"],
    "recherche_specialite": ["getListSecteurActivitesPS", "getListSpecialiteBySecteurActivite",
                             "getListVilleAndGouvernorat"],
    "facture": ["searchFacture"],
    "facture_ps": ["searchListFactureByPs", "getFacturePsByIdTier"],
}


@pytest.mark.parametrize("service_key,ops", TARGET_OPS.items())
def test_wsdl_parses_offline_and_has_operations(service_key, ops):
    pytest.importorskip("zeep")
    if not os.path.isdir(WSDL_DIR):
        pytest.skip(f"WSDL dir not found: {WSDL_DIR}")

    soap.reset_soap_clients()
    client = soap._get_client(service_key)

    available = set()
    for binding in client.wsdl.bindings.values():
        available |= set(getattr(binding, "_operations", {}).keys())
    for op in ops:
        assert op in available, f"{op} missing from {service_key} (have: {sorted(available)[:8]}...)"


# ──────────────────────────────────────────────────────────────
# 2. Mappers (no network, no zeep)
# ──────────────────────────────────────────────────────────────
def test_map_contrat():
    dto = {
        "numContrat": "C-12345",
        "dateEffet": "2023-01-01",
        "dateFinEffet": None,
        "qualite": {"code": "1", "libelle": "Titulaire"},
        "situation": {"libelle": "Actif"},
        "vip": False,
        "personnePhysique": {"nomComplet": "Nadia Mansour", "numeroPolice": "P-9001"},
    }
    out = soap._map_contrat(dto)
    assert out["num_contrat"] == "C-12345"
    assert out["qualite"] == "Titulaire"
    assert out["situation"] == "Actif"
    assert out["titulaire"] == "Nadia Mansour"
    assert out["num_police"] == "P-9001"


def test_map_beneficiaire():
    dto = {
        "nom": "Mansour", "prenom": "Sami", "nomComplet": "Sami Mansour",
        "dateNaissance": "2015-06-12", "age": 11,
        "codeCntr": {"libelle": "Enfant"}, "enRegle": True, "montantDisponible": 600.0,
    }
    out = soap._map_beneficiaire(dto)
    assert out["nom_complet"] == "Sami Mansour"
    assert out["lien"] == "Enfant"
    assert out["couverture_active"] is True
    assert out["montant_disponible"] == 600.0


def test_map_remboursement_list():
    dto = {
        "resultSize": 2,
        "contextLPResult": {
            "mntTotalRemb": 1245.0, "mntTotalRegler": 1100.0,
            "mntResteAchargeAdherent": 145.0, "ttMutuelle": 900.0,
        },
        "listResultEntityObject": [
            {"numDossier": "DOS-1", "mntRemb": 50.0},
            # Untyped wrapper rows (no structural keys) are stripped entirely —
            # they could carry PII the shield can't recognize.
            {"array": ["opaque blob"]},
        ],
    }
    out = soap._map_remboursement_list(dto)
    assert out["result_size"] == 2
    assert out["totaux"]["total_rembourse"] == 1245.0
    assert out["totaux"]["reste_a_charge"] == 145.0
    assert out["dossiers"] == [{"numDossier": "DOS-1", "mntRemb": 50.0}]


def test_map_reclamation():
    dto = {
        "numeroReclamation": "REC-001",
        "objetReclamation": "Remboursement tardif",
        "descreptionReclamation": "Mon dossier traîne",
        "formattedDate": "2024-03-10",
        "statut": {"libelle": "En cours"},
        "statutForMobile": "EN_COURS",
        "natureReclamation": "Délai",
        "typeReclamation": {"libelle": "Remboursement"},
        "numDossier": "DOS-9901",
        "reponseExtarnet": "En traitement",
    }
    out = soap._map_reclamation(dto)
    assert out["numero"] == "REC-001"
    assert out["objet"] == "Remboursement tardif"
    assert out["statut"] == "EN_COURS"            # statutForMobile preferred
    assert out["type"] == "Remboursement"
    assert out["reponse"] == "En traitement"


def test_as_list_normalization():
    assert soap._as_list(None) == []
    assert soap._as_list({"a": 1}) == [{"a": 1}]
    assert soap._as_list([1, 2]) == [1, 2]


def test_ref_label_variants():
    assert soap._ref_label({"libelle": "Actif", "code": "1"}) == "Actif"
    assert soap._ref_label({"code": "X"}) == "X"
    assert soap._ref_label(None) is None
    assert soap._ref_label("plain") == "plain"


# ──────────────────────────────────────────────────────────────
# 3. Graph node fallback (SOAP raises → mock)
# ──────────────────────────────────────────────────────────────
def test_dossier_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import lookups

    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("server unreachable (off-LAN)")

    monkeypatch.setattr(soap, "get_contrat_adherent", _boom)
    monkeypatch.setattr(soap, "get_list_remboursement", _boom)

    state = {"matricule": "12345"}
    out = asyncio.run(lookups.dossier_lookup_node(state))

    # Real mode must NOT fabricate mock personal data — honest notice instead
    assert out["system_records"]["service_indisponible"] is True
    assert "dossiers" not in out["system_records"]


def test_beneficiary_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import lookups

    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("server unreachable (off-LAN)")

    monkeypatch.setattr(soap, "get_beneficiaires", _boom)

    state = {"matricule": "12345"}
    out = asyncio.run(lookups.beneficiary_lookup_node(state))

    assert out["system_records"]["service_indisponible"] is True
    assert "beneficiaires" not in out["system_records"]


def test_dossier_node_mock_path_when_toggle_off(monkeypatch):
    from backend.domain.graph.nodes import lookups

    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", False, raising=False)
    out = asyncio.run(lookups.dossier_lookup_node({"matricule": "12345"}))
    assert out["system_records"]["plafond_annuel"] == 5000.0


# ──────────────────────────────────────────────────────────────
# 4. Personal-lookup classifier (réclamations + dossier detail routing)
# ──────────────────────────────────────────────────────────────
def test_extract_dossier_number():
    from backend.domain.graph import routing
    assert routing.extract_dossier_number("détail du dossier DOS-2026-0042 svp") == "DOS-2026-0042"
    assert routing.extract_dossier_number("référence 88921") == "88921"
    assert routing.extract_dossier_number("aucun numéro ici") is None
    # Years and round amounts must NOT pass for dossier references
    assert routing.extract_dossier_number("mes remboursements de 2024") is None
    assert routing.extract_dossier_number("le plafond est 2000 TND") is None


def test_classify_personal_lookup_routes():
    from backend.domain.graph import routing
    assert routing.classify_personal_lookup("Où en sont mes réclamations ?") == "reclamation_lookup"
    assert routing.classify_personal_lookup("le détail du dossier DOS-2026-0042") == "dossier_detail_lookup"
    assert routing.classify_personal_lookup("qui sont mes bénéficiaires et ma famille ?") == "beneficiary_lookup"
    assert routing.classify_personal_lookup("montre mes dossiers de remboursement") == "dossier_lookup"


# ──────────────────────────────────────────────────────────────
# 5. New lookup nodes: réclamations + dossier detail (real + fallback)
# ──────────────────────────────────────────────────────────────
def test_reclamation_node_real_success(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _ok(*a, **k):
        return [{"numero": "R1", "objet": "x", "statut": "En cours"}]

    monkeypatch.setattr(soap, "get_list_reclamation", _ok)
    out = asyncio.run(lookups.reclamation_lookup_node({"matricule": "12345"}))
    assert out["system_records"]["nombre_reclamations"] == 1
    assert out["system_records"]["reclamations"][0]["numero"] == "R1"


def test_reclamation_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(soap, "get_list_reclamation", _boom)
    out = asyncio.run(lookups.reclamation_lookup_node({"matricule": "12345"}))
    assert out["system_records"]["service_indisponible"] is True
    assert "reclamations" not in out["system_records"]


def test_reclamation_node_mock_when_toggle_off(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", False, raising=False)
    out = asyncio.run(lookups.reclamation_lookup_node({"matricule": "12345"}))
    assert out["system_records"]["nombre_reclamations"] == 2          # demo mock


def test_dossier_detail_node_real_success(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    captured = {}

    async def _ok(num):
        captured["num"] = num
        return {"num_dossier": num, "statut": "rembourse"}

    monkeypatch.setattr(soap, "get_dossier_remboursement", _ok)
    state = {"matricule": "12345", "messages": [HumanMessage(content="détail du dossier DOS-2026-0042")]}
    out = asyncio.run(lookups.dossier_detail_lookup_node(state))

    assert captured["num"] == "DOS-2026-0042"                          # number parsed from message
    assert out["system_records"]["dossier_detail"]["statut"] == "rembourse"


def test_dossier_detail_node_degrades_honestly_in_real_mode(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(soap, "get_dossier_remboursement", _boom)
    state = {"matricule": "12345", "messages": [HumanMessage(content="détail du dossier DOS-2026-0042")]}
    out = asyncio.run(lookups.dossier_detail_lookup_node(state))

    assert out["system_records"]["service_indisponible"] is True


def test_dossier_detail_real_mode_requires_number(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    state = {"matricule": "12345", "messages": [HumanMessage(content="le détail de mon dossier svp")]}
    out = asyncio.run(lookups.dossier_detail_lookup_node(state))

    # No fabrication: asks for the missing number instead
    assert out["system_records"]["dossier_detail"] is None
    assert "precision_requise" in out["system_records"]


# ──────────────────────────────────────────────────────────────
# 6. Cache policy — personal/per-user responses must NOT be cached (PII safety)
# ──────────────────────────────────────────────────────────────
def test_cache_policy_blocks_personal_responses():
    from backend.services.cache_policy import is_cacheable_response

    base = {"confidence": 95, "source": "claims_graph", "degraded": False}

    # User-agnostic knowledge answer → cacheable
    assert is_cacheable_response({**base, "intent": "info_query", "tools_called": ["rag_retrieval"]}) is True

    # Every personal lookup → NOT cacheable (would leak across users)
    for tool in ["dossier_lookup", "beneficiary_lookup", "reclamation_lookup", "dossier_detail_lookup"]:
        assert is_cacheable_response({**base, "intent": "personal_lookup", "tools_called": [tool]}) is False, tool

    # Claim action (echoes user's own claim data) → NOT cacheable
    assert is_cacheable_response({**base, "intent": "claim_action", "tools_called": ["claim_extraction"]}) is False

    # Other guards still hold
    info = {**base, "intent": "info_query"}
    assert is_cacheable_response({**info, "confidence": 50}) is False     # low confidence
    assert is_cacheable_response({**info, "degraded": True}) is False     # degraded
    assert is_cacheable_response({**info, "source": "simulated"}) is False  # untrusted source
    assert is_cacheable_response(info, cache_hit=True) is False           # already a hit
    assert is_cacheable_response(None) is False


# ──────────────────────────────────────────────────────────────
# 7. Write-back: réclamation creation + claim-submission client surface
# ──────────────────────────────────────────────────────────────
def test_create_reclamation_maps_response(monkeypatch):
    async def _call_stub(service, op, **k):
        assert op == "createReclamation"
        return {"numeroReclamation": "REC-9", "objetReclamation": "x", "statutForMobile": "NEW"}

    monkeypatch.setattr(soap, "_call", _call_stub)
    out = asyncio.run(soap.create_reclamation("12345", "titre", "desc"))
    assert out["numero"] == "REC-9"
    assert out["statut"] == "NEW"


def test_create_bs_digital_returns_reference(monkeypatch):
    async def _call_stub(service, op, **k):
        assert op == "createBsDigital"
        return "BS-REF-123"

    monkeypatch.setattr(soap, "_call", _call_stub)
    out = asyncio.run(soap.create_bs_digital(matricule="12345", reference_bs="X"))
    assert out == "BS-REF-123"


def test_escalation_files_real_reclamation(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import escalation

    monkeypatch.setattr(escalation.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _ok(**k):
        return {"numero": "REC-2026-777"}

    monkeypatch.setattr(soap, "create_reclamation", _ok)
    state = {"matricule": "12345",
             "messages": [HumanMessage(content="je veux déposer une réclamation, c'est inacceptable")]}
    out = asyncio.run(escalation.escalation_node(state))

    assert out["escalation_ticket"]["case_id"] == "REC-2026-777"
    assert "REC-2026-777" in out["final_response"]
    assert out["claim_status"] == "pending_human"


def test_escalation_falls_back_to_stub(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import escalation

    monkeypatch.setattr(escalation.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(**k):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(soap, "create_reclamation", _boom)
    # Explicit filing phrasing so the write path is actually exercised
    state = {"matricule": "12345", "messages": [HumanMessage(content="je veux déposer une réclamation")]}
    out = asyncio.run(escalation.escalation_node(state))

    assert out["escalation_ticket"]["case_id"] == "ESC-STUB-001"
    assert out["claim_status"] == "pending_human"


def test_escalation_does_not_file_on_anger(monkeypatch):
    """Anger/human-request alone must NEVER create an ERP record."""
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import escalation

    monkeypatch.setattr(escalation.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _must_not_be_called(**k):
        raise AssertionError("create_reclamation called without explicit filing intent")

    monkeypatch.setattr(soap, "create_reclamation", _must_not_be_called)
    for msg in ["votre service est nul", "passez-moi un responsable", "où en sont mes réclamations ?"]:
        state = {"matricule": "12345", "messages": [HumanMessage(content=msg)]}
        out = asyncio.run(escalation.escalation_node(state))
        assert out["escalation_ticket"]["case_id"] == "ESC-STUB-001", msg
        assert out["claim_status"] == "pending_human"


def test_escalation_stub_when_toggle_off(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import escalation

    monkeypatch.setattr(escalation.settings, "IWAY_USE_REAL_API", False, raising=False)
    state = {"matricule": "12345", "messages": [HumanMessage(content="un agent")]}
    out = asyncio.run(escalation.escalation_node(state))

    assert out["escalation_ticket"]["case_id"] == "ESC-STUB-001"


# ──────────────────────────────────────────────────────────────
# 8. Code-review fixes: PII shield, cache lookup gate, confidence
#    signal, partial gather failure, escalation without numéro
# ──────────────────────────────────────────────────────────────
def test_pii_guard_pseudonymize_and_restore():
    import json
    from backend.services import pii_guard

    records = {
        "beneficiaires": [
            {"nom": "Tounsi", "prenom": "Ahmed", "lien": "titulaire", "date_naissance": "1985-06-12"},
        ],
        "contrat": {"titulaire": "Nadia Mansour", "num_contrat": "C-12345"},
    }
    sanitized, mapping = pii_guard.pseudonymize_records(records)
    blob = json.dumps(sanitized, ensure_ascii=False)

    # Identifying values are gone from what the LLM would see
    for secret in ("Tounsi", "Ahmed", "Nadia Mansour", "1985-06-12"):
        assert secret not in blob, secret
    # Structural fields stay readable
    assert sanitized["contrat"]["num_contrat"] == "C-12345"
    assert sanitized["beneficiaires"][0]["lien"] == "titulaire"

    # Restoration puts the real values back into the drafted text
    draft = f"Le titulaire est {sanitized['contrat']['titulaire']}."
    assert "Nadia Mansour" in pii_guard.restore_pii(draft, mapping)


def test_pii_shield_active_only_for_external_llm(monkeypatch):
    from backend.services import pii_guard

    monkeypatch.setattr(pii_guard.settings, "USE_LOCAL_LLM", False, raising=False)
    assert pii_guard.pii_shield_active() is True   # external Gemini → shield on
    monkeypatch.setattr(pii_guard.settings, "USE_LOCAL_LLM", True, raising=False)
    assert pii_guard.pii_shield_active() is False  # on-prem Ollama → shield off


def test_is_personal_query_gates_cache_lookup():
    from backend.services.cache_policy import is_personal_query

    assert is_personal_query("mes remboursements ?") is True
    assert is_personal_query("Mon dossier dentaire") is True
    assert is_personal_query("détail du dossier DOS-2026-0042") is True   # reference number
    assert is_personal_query("liste les bénéficiaires") is True           # possessive-less imperative
    assert is_personal_query("affiche les remboursements en cours") is True
    assert is_personal_query("comment déposer une réclamation ?") is False  # generic → cacheable
    assert is_personal_query("") is False


def test_has_meaningful_records_rejects_empty_real_shell():
    from backend.domain.graph.nodes.draft_response import _has_meaningful_records

    # Real API reachable but returned nothing → must NOT trigger the db signal
    empty_shell = {
        "contrat": None,
        "remboursements": {"result_size": 0, "totaux": {}, "dossiers": []},
        "dossiers": [],
    }
    assert _has_meaningful_records(empty_shell) is False
    assert _has_meaningful_records({}) is False

    # Populated shapes from every lookup → signal fires
    assert _has_meaningful_records({"dossiers": [{"id": "D1"}]}) is True
    assert _has_meaningful_records({"beneficiaires": [{"nom": "x"}]}) is True
    assert _has_meaningful_records({"reclamations": [{"numero": "R1"}]}) is True
    assert _has_meaningful_records({"dossier_detail": {"num_dossier": "D1"}}) is True
    assert _has_meaningful_records({"contrat": {"num_contrat": "C1"}}) is True


def test_dossier_lookup_partial_failure_keeps_partial_result(monkeypatch):
    from backend.domain.graph.nodes import lookups

    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _contrat_boom(*a, **k):
        raise RuntimeError("contrat service down")

    async def _remb_ok(*a, **k):
        return {"result_size": 1, "totaux": {}, "dossiers": [{"id": "DOS-REAL-1"}]}

    monkeypatch.setattr(soap, "get_contrat_adherent", _contrat_boom)
    monkeypatch.setattr(soap, "get_list_remboursement", _remb_ok)

    out = asyncio.run(lookups.dossier_lookup_node({"matricule": "12345"}))

    # One failure → partial real result, NOT the full mock fallback
    assert out["system_records"]["contrat"] is None
    assert out["system_records"]["dossiers"][0]["id"] == "DOS-REAL-1"


def test_escalation_acknowledges_reclamation_without_numero(monkeypatch):
    from langchain_core.messages import HumanMessage
    from backend.domain.graph.nodes import escalation

    monkeypatch.setattr(escalation.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _created_no_numero(**k):
        return {"numero": None, "objet": "x"}   # created, numéro assigned async

    monkeypatch.setattr(soap, "create_reclamation", _created_no_numero)
    state = {"matricule": "12345", "messages": [HumanMessage(content="je veux porter plainte maintenant")]}
    out = asyncio.run(escalation.escalation_node(state))

    # Must acknowledge the filing (no stub, no silent duplicate-inducing message)
    assert out["escalation_ticket"]["case_id"] == "REC-EN-ATTENTE"
    assert out["escalation_ticket"]["type"] == "reclamation"
    assert "enregistrée" in out["final_response"]


# ──────────────────────────────────────────────────────────────
# 9. Review round 2: write safety, routing dominance, shield gaps
# ──────────────────────────────────────────────────────────────
def test_writes_never_retry(monkeypatch):
    """Non-idempotent SOAP writes must pass _retries=1 (a timeout after a
    server-side success would otherwise file a duplicate)."""
    captured = {}

    async def _call_spy(service, op, _retries=2, **k):
        captured[op] = _retries
        return None

    monkeypatch.setattr(soap, "_call", _call_spy)
    asyncio.run(soap.create_reclamation("12345", "t", "d"))
    asyncio.run(soap.create_bs_digital(matricule="12345"))

    assert captured["createReclamation"] == 1
    assert captured["createBsDigital"] == 1


def test_route_after_decompose_escalation_dominates():
    from backend.domain.graph.routing import route_after_decompose

    state = {
        "sub_intents": [
            {"intent": "personal_lookup", "query": "liste mes dossiers"},
            {"intent": "escalation", "query": "je veux parler à un agent"},
        ],
    }
    # Explicit human request must not be silently dropped by the multi-executor
    assert route_after_decompose(state) == "escalation"


def test_pii_guard_tokenizes_non_string_values():
    import json
    from datetime import date
    from backend.services import pii_guard

    records = {"beneficiaires": [{"nom": "Tounsi", "date_naissance": date(1985, 6, 12)}]}
    sanitized, mapping = pii_guard.pseudonymize_records(records)
    blob = json.dumps(sanitized, ensure_ascii=False, default=str)

    assert "1985-06-12" not in blob          # date object shielded too
    assert "1985-06-12" in mapping.values()


def test_project_row_drops_unknown_keys():
    row = {
        "numDossier": "D-1",
        "mntRembourse": 126.0,
        "statut": "regle",
        "nomAdherent": "SECRET NAME",        # unknown-shape PII → dropped
        "observation": "texte libre",        # unmatched key → dropped
    }
    out = soap._project_row(row)
    assert out["numDossier"] == "D-1"
    assert out["mntRembourse"] == 126.0
    assert "nomAdherent" not in out
    assert "observation" not in out


def test_compliance_flags_foreign_currency():
    from backend.domain.graph.nodes.compliance_check import compliance_check_node

    state = {"draft_response": "Le montant total s'élève à 180.0€ remboursé.", "confidence": 0.9}
    out = asyncio.run(compliance_check_node(state))
    assert any("CURRENCY" in n for n in out["compliance_notes"])
    assert out["confidence"] < 0.9

    state_ok = {"draft_response": "Le montant est de 180 TND.", "confidence": 0.9}
    out_ok = asyncio.run(compliance_check_node(state_ok))
    assert not any("CURRENCY" in n for n in out_ok["compliance_notes"])


def test_map_remboursement_list_projects_rows():
    dto = {
        "resultSize": 1,
        "contextLPResult": {"mntTotalRemb": 100.0},
        "listResultEntityObject": [{"numDossier": "D-9", "nomAdherent": "SECRET"}],
    }
    out = soap._map_remboursement_list(dto)
    assert out["dossiers"] == [{"numDossier": "D-9"}]   # name stripped


# ══════════════════════════════════════════════════════════════
# WAVE 2 — new services (auth identity, providers, plafonds, factures)
# ══════════════════════════════════════════════════════════════

# ── 10. New mappers ──────────────────────────────────────────
def test_map_identity_extracts_activation_fields():
    dto = {
        "numContrat": "C-1",
        "personnePhysique": {
            "nom": "Mansour", "prenom": "Nadia", "nomComplet": "Nadia Mansour",
            "dateNaissance": "1985-06-12", "numeroPieceId": "09876543",
            "numeroPolice": "12012500000011",
        },
    }
    out = soap._map_identity(dto)
    assert out["nom"] == "Mansour"
    assert out["date_naissance"] == "1985-06-12"
    assert out["cin"] == "09876543"
    assert out["num_police"] == "12012500000011"


def test_map_prestataire_from_real_shape():
    # Shape captured from the live searchPsWithConvTP response (web-s/)
    dto = {
        "nom": " LABORATOIRE MEMMI AND MAHJOUBI (LAB2M)",
        "numTelBureau": "", "numTelFixe": "71830388", "numTelMobile": "98348038",
        "secteurActivite": "Centre Analyse Médical", "specialite": "",
        "adresse": {
            "adresse": "35,RUE DE PALESTINE  ",
            "gouvernorat": {"libelle": "Tunis"},
            "ville": {"libelle": ""},
        },
    }
    out = soap._map_prestataire(dto)
    assert out["nom"] == "LABORATOIRE MEMMI AND MAHJOUBI (LAB2M)"   # stripped
    assert out["secteur"] == "Centre Analyse Médical"
    assert out["specialite"] is None                                  # empty → None
    assert out["gouvernorat"] == "Tunis"
    assert out["ville"] is None                                       # empty libelle → None
    assert out["telephone"] == "71830388"                             # fixe preferred
    assert out["conventionne"] is True


def test_map_plafond_defensive_fields():
    dto = {
        "beneficiaire": {"nomComplet": "Fatma Tounsi"},
        "lienParental": {"libelle": "Conjoint"},
        "montantPlafond": 3000.0, "montantConsomme": 410.0, "montantDisponible": 2590.0,
    }
    out = soap._map_plafond(dto)
    assert out["beneficiaire"] == "Fatma Tounsi"
    assert out["lien"] == "Conjoint"
    assert out["montant_disponible"] == 2590.0


def test_map_facture_projects_then_plucks():
    # FacturePsDto carries name fields — they must be DROPPED by the whitelist
    # before any pluck (matriculeAdh is whitelisted-but-unplucked: also absent).
    dto = {
        "reference": "231FACTMP710602YPC000",
        "dateCreation": "2026-04-22",
        "mntFacture": 1840.0,
        "natureFacture": "Facture temporaire",
        "nomPs": "SECRET PROVIDER",
        "nomAdherent": "SECRET NAME",
    }
    out = soap._map_facture(dto)
    assert out["num_facture"] == "231FACTMP710602YPC000"
    assert out["date"] == "2026-04-22"
    assert out["montant"] == 1840.0
    assert out["nature"] == "Facture temporaire"
    assert "SECRET" not in str(out)


def test_search_prestataires_filters_and_caps(monkeypatch):
    rows = (
        [{"nom": f"Dr Cardio {i}", "specialite": "Cardiologie",
          "secteurActivite": "Médecin",
          "adresse": {"gouvernorat": {"libelle": "Sousse"}, "ville": {"libelle": "Sousse"}, "adresse": "x"}}
         for i in range(12)]
    )
    extra = [{"nom": "Dr Dermato", "specialite": "Dermatologie",
              "secteurActivite": "Médecin",
              "adresse": {"gouvernorat": {"libelle": "Tunis"}, "ville": {"libelle": ""}, "adresse": "y"}}]

    async def _call_stub(service, op, **k):
        assert op == "searchPsWithConvTP"
        return list(rows) + extra

    monkeypatch.setattr(soap, "_call", _call_stub)
    out = asyncio.run(soap.search_prestataires(specialite="cardiologie", gouvernorat="sousse"))

    assert len(out) == soap.settings.PROVIDER_SEARCH_MAX_RESULTS      # capped
    assert all("Cardio" in r["nom"] for r in out)                     # client-side refinement
    assert all(r["gouvernorat"] == "Sousse" for r in out)


def test_get_contrat_ps_by_matricule_fiscal_returns_id_tiers(monkeypatch):
    async def _call_stub(service, op, **k):
        assert op == "getContratPsByMatriculeFiscal"
        return "151537"

    monkeypatch.setattr(soap, "_call", _call_stub)
    out = asyncio.run(soap.get_contrat_ps_by_matricule_fiscal("0710602Y"))
    assert out == {"id_tiers": "151537"}


def test_existing_reads_pass_num_police(monkeypatch):
    """The live ERP REQUIRES numPolice on the adherent reads — regression guard
    for the previously-missing parameter."""
    captured = {}

    async def _call_spy(service, op, _retries=2, **k):
        captured[op] = k
        return None

    monkeypatch.setattr(soap, "_call", _call_spy)
    asyncio.run(soap.get_contrat_adherent("10012", "POL-1"))
    asyncio.run(soap.get_beneficiaires("10012", "POL-1"))
    asyncio.run(soap.get_list_remboursement("10012", "POL-1"))
    asyncio.run(soap.get_list_reclamation("10012", "POL-1"))

    assert captured["getContratAdherentByMatricule"]["numPolice"] == "POL-1"
    assert captured["getListeBeneficiairesByMatricule"]["numPolice"] == "POL-1"
    assert captured["getListRemboursementByMatricule"]["numPolice"] == "POL-1"
    assert captured["getListReclamationByMatricule"]["numPolice"] == "POL-1"


# ── 11. New lookup nodes: plafonds + factures (role-aware) ──
def test_plafond_node_mock_when_toggle_off(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", False, raising=False)
    out = asyncio.run(lookups.plafond_lookup_node({"matricule": "12345"}))
    assert out["system_records"]["nombre_beneficiaires"] == 3
    assert out["system_records"]["plafonds"][0]["montant_plafond"] == 5000.0


def test_plafond_node_real_success(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    captured = {}

    async def _ok(matricule, num_police=""):
        captured["num_police"] = num_police
        return [{"beneficiaire": "X", "montant_plafond": 1000.0}]

    monkeypatch.setattr(soap, "get_plafonds_beneficiaires", _ok)
    out = asyncio.run(lookups.plafond_lookup_node({"matricule": "10012", "num_police": "POL-1"}))
    assert captured["num_police"] == "POL-1"
    assert out["system_records"]["plafonds"][0]["montant_plafond"] == 1000.0


def test_plafond_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("FAULT 3 — pas de bénéficiaires (test data)")

    monkeypatch.setattr(soap, "get_plafonds_beneficiaires", _boom)
    out = asyncio.run(lookups.plafond_lookup_node({"matricule": "10012"}))
    assert out["system_records"]["service_indisponible"] is True
    assert "plafonds" not in out["system_records"]


def test_facture_node_mock_both_roles(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", False, raising=False)

    out_adh = asyncio.run(lookups.facture_lookup_node({"matricule": "12345", "role": "Adherent"}))
    assert out_adh["system_records"]["role_vue"] == "adherent"

    out_ps = asyncio.run(lookups.facture_lookup_node({"matricule": "99999", "role": "Prestataire"}))
    assert out_ps["system_records"]["role_vue"] == "prestataire"
    assert out_ps["system_records"]["factures"][0]["num_facture"].startswith("FACT-")


def test_facture_node_real_role_aware(monkeypatch):
    """Prestataire + id_tiers → search_factures_ps; Adherent → searchFacture."""
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    calls = {}

    async def _ps(id_tiers, **k):
        calls["ps"] = id_tiers
        return {"result_size": 1, "factures": [{"num_facture": "F-PS"}]}

    async def _adh(matricule, num_police="", **k):
        calls["adh"] = (matricule, num_police)
        return {"result_size": 1, "factures": [{"num_facture": "F-ADH"}]}

    monkeypatch.setattr(soap, "search_factures_ps", _ps)
    monkeypatch.setattr(soap, "search_factures_adherent", _adh)

    out = asyncio.run(lookups.facture_lookup_node(
        {"matricule": "0710602Y", "role": "Prestataire", "id_tiers": "151537"}))
    assert calls["ps"] == "151537"
    assert out["system_records"]["role_vue"] == "prestataire"

    out = asyncio.run(lookups.facture_lookup_node(
        {"matricule": "10012", "role": "Adherent", "num_police": "POL-1"}))
    assert calls["adh"] == ("10012", "POL-1")
    assert out["system_records"]["role_vue"] == "adherent"


def test_facture_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import lookups
    monkeypatch.setattr(lookups.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(soap, "search_factures_adherent", _boom)
    out = asyncio.run(lookups.facture_lookup_node({"matricule": "10012", "role": "Adherent"}))
    assert out["system_records"]["service_indisponible"] is True
    assert "factures" not in out["system_records"]


# ── 12. Provider search node ─────────────────────────────────
def _provider_state(text):
    from langchain_core.messages import HumanMessage
    return {"matricule": "12345", "messages": [HumanMessage(content=text)]}


def _stub_gouvernorats(monkeypatch):
    """Real-mode known_gouvernorats() would hit Redis + the live referential —
    pin it to the static list so tests stay fast and offline."""
    from backend.services import referentials

    async def _static():
        return list(referentials.GOUVERNORATS_TN)

    monkeypatch.setattr(referentials, "known_gouvernorats", _static)


def test_provider_node_mock_filters(monkeypatch):
    from backend.domain.graph.nodes import provider_search as ps
    monkeypatch.setattr(ps.settings, "IWAY_USE_REAL_API", False, raising=False)

    out = asyncio.run(ps.provider_search_node(_provider_state(
        "trouve-moi un cardiologue conventionné à Sousse")))
    records = out["system_records"]
    assert records["criteres"] == {"specialite": "Cardiologie", "gouvernorat": "Sousse"}
    assert records["prestataires"], "mock should return at least one row"
    assert all(p["specialite"] == "Cardiologie" for p in records["prestataires"])


def test_provider_node_real_success(monkeypatch):
    from backend.domain.graph.nodes import provider_search as ps
    monkeypatch.setattr(ps.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_gouvernorats(monkeypatch)

    captured = {}

    async def _search(specialite="", gouvernorat="", num_police="", **k):
        captured.update(specialite=specialite, gouvernorat=gouvernorat)
        return [{"nom": "Dr X", "specialite": "Cardiologie", "gouvernorat": "Sousse", "conventionne": True}]

    monkeypatch.setattr(soap, "search_prestataires", _search)
    out = asyncio.run(ps.provider_search_node(_provider_state("un cardiologue à Sousse")))

    assert captured == {"specialite": "Cardiologie", "gouvernorat": "Sousse"}
    assert out["system_records"]["nombre_resultats"] == 1


def test_provider_node_real_requires_filters(monkeypatch):
    """Real mode must NOT pull the unfiltered ~1 MB directory — it asks the
    user to narrow the search instead."""
    from backend.domain.graph.nodes import provider_search as ps
    monkeypatch.setattr(ps.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_gouvernorats(monkeypatch)

    async def _must_not_be_called(**k):
        raise AssertionError("unfiltered directory pull")

    monkeypatch.setattr(soap, "search_prestataires", _must_not_be_called)
    out = asyncio.run(ps.provider_search_node(_provider_state("je cherche un prestataire")))

    assert out["system_records"]["prestataires"] == []
    assert "precision_requise" in out["system_records"]


def test_provider_node_degrades_honestly_in_real_mode(monkeypatch):
    from backend.domain.graph.nodes import provider_search as ps
    monkeypatch.setattr(ps.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_gouvernorats(monkeypatch)

    async def _boom(**k):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(soap, "search_prestataires", _boom)
    out = asyncio.run(ps.provider_search_node(_provider_state("un dentiste à Sfax")))
    assert out["system_records"]["service_indisponible"] is True


# ── 13. Classifier routes for the new personal tools ─────────
def test_classify_personal_lookup_wave2_routes():
    from backend.domain.graph import routing
    assert routing.classify_personal_lookup("mes factures en cours") == "facture_lookup"
    assert routing.classify_personal_lookup("où en est ma facture ?") == "facture_lookup"
    assert routing.classify_personal_lookup("mon plafond restant") == "plafond_lookup"
    assert routing.classify_personal_lookup("combien ai-je consommé ?") == "plafond_lookup"
    # Pre-existing routes must be unchanged
    assert routing.classify_personal_lookup("Où en sont mes réclamations ?") == "reclamation_lookup"
    assert routing.classify_personal_lookup("montre mes dossiers de remboursement") == "dossier_lookup"
