"""
I-Way SOAP Client — Async wrapper over the real I-Way Axis2 web services.

The production I-Way ERP exposes Apache Axis2 SOAP services (document/literal),
not REST. This module wraps four of them and maps their verbose DTOs down to the
compact ``system_records`` dicts the graph already consumes
(see backend/domain/graph/nodes/draft_response.py).

Services / operations used:
  - contratAdherentWSMeg   → getContratAdherentByMatricule        (Contrat + identité activation)
                             getListeBeneficiairesByMatricule     (Bénéficiaires)
                             getListPlafondBeneficiairesByMatricule (Plafonds/consommation)
  - remboursementAdherentWS→ getListRemboursementByMatricule      (Liste remboursements)
                             getDossierRemboursementByNumDossier  (Détail dossier)
  - reclamationWS          → getListReclamationByMatricule        (Liste réclamations)
  - prestatiareWS          → searchPsWithConvTP                   (Recherche PS conventionnés)
  - rechercheSpecialiteWS  → getListSecteurActivitesPS / getListSpecialiteBySecteurActivite
                             / getListVilleAndGouvernorat         (Référentiels recherche)
  - factureWS              → searchFacture                        (Factures adhérent)
  - facturePsWS            → searchListFactureByPs                (Factures prestataire)
  - contratPsWS            → getContratPsByMatriculeFiscal / getContratPsByIdTiers
                             (Identité prestataire — activation)

Design notes:
  * zeep is synchronous; every call is offloaded to a worker thread via
    ``anyio.to_thread.run_sync`` so the FastAPI event loop is never blocked.
  * WSDLs are loaded from local files (IWAY_SOAP_WSDL_DIR) so the clients build
    and validate fully OFFLINE. The live ``soap:address`` baked into each WSDL is
    only contacted when an operation is actually invoked — which requires the
    company LAN (server 192.168.111.102:8080).
  * Auth is HTTP Basic at the Axis2 container (admin/admin by default), configurable.
  * Calls are guarded by the shared ``api_circuit`` breaker + retry/backoff; callers
    (the graph nodes) fall back to mock data on failure for graceful degradation.

Toggle: only used when IWAY_USE_REAL_API=true. Otherwise the REST mock
(backend/routers/iway_mock.py via backend/services/iway_client.py) is used.
"""

import os
import re
import logging
from functools import lru_cache
from typing import Any, Optional

import anyio

from backend.config import get_settings
from backend.services.resilience import api_circuit, retry_with_backoff

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# ERP latency is the most failure-prone dependency — make every SOAP call a span.
try:
    from opentelemetry import trace as _otel_api
    from opentelemetry.trace import Status as _OtelStatus, StatusCode as _OtelStatusCode
    _soap_tracer = _otel_api.get_tracer("iway.soap")
except ImportError:  # pragma: no cover — telemetry is optional
    _soap_tracer = None


# ──────────────────────────────────────────────────────────────
# WSDL filenames per service (bundled in IWAY_SOAP_WSDL_DIR)
# ──────────────────────────────────────────────────────────────
_WSDL_FILES = {
    "contrat": "contratAdherentWSMeg.xml",
    "remboursement": "remboursementAdherentWS.xml",
    "reclamation": "reclamationWS.xml",
    "contrat_ps": "contratPsWS.xml",
    "prestataire_search": "prestatiareWS.xml",
    "recherche_specialite": "rechercheSpecialiteWS.xml",
    "facture": "factureWS.xml",
    "facture_ps": "facturePsWS.xml",
}

# Remote ?wsdl URLs (used when IWAY_SOAP_LOAD_LOCAL_WSDL=false, i.e. on-site)
_WSDL_REMOTE = {
    "contrat": "/contratAdherentWSMeg?wsdl",
    "remboursement": "/remboursementAdherentWS?wsdl",
    "reclamation": "/reclamationWS?wsdl",
    "contrat_ps": "/contratPsWS?wsdl",
    "prestataire_search": "/prestatiareWS?wsdl",
    "recherche_specialite": "/rechercheSpecialiteWS?wsdl",
    "facture": "/factureWS?wsdl",
    "facture_ps": "/facturePsWS?wsdl",
}


def _default_wsdl_dir() -> str:
    """Default bundled WSDL directory: <repo_root>/Webservices."""
    # this file lives at <repo>/backend/services/iway_soap_client.py
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "Webservices")


def _wsdl_location(service_key: str) -> str:
    """Resolve the WSDL location (local file path or remote ?wsdl URL)."""
    if settings.IWAY_SOAP_LOAD_LOCAL_WSDL:
        wsdl_dir = settings.IWAY_SOAP_WSDL_DIR or _default_wsdl_dir()
        path = os.path.join(wsdl_dir, _WSDL_FILES[service_key])
        return path
    return settings.IWAY_SOAP_BASE_URL.rstrip("/") + _WSDL_REMOTE[service_key]


# Known Axis2/ADB WSDL defects patched before zeep parses them.
# Axis2 emits a few Java class names as if they were XML Schema built-ins
# (`xs:Enum` for enum holders, `xs:RuntimeException` in the fault schema). These
# are not real XSD types, so zeep's resolver throws. None are used by the
# operations we call, so we rewrite them to the valid built-in xs:anyType.
_WSDL_SANITIZE = [
    (b'base="xs:Enum"', b'base="xs:anyType"'),
    (b'type="xs:Enum"', b'type="xs:anyType"'),
    (b'base="xs:RuntimeException"', b'base="xs:anyType"'),
    (b'type="xs:RuntimeException"', b'type="xs:anyType"'),
]

# Temp files holding sanitized WSDL copies (we never mutate the bundled originals).
_temp_wsdl_paths: list[str] = []


def _read_wsdl_bytes(service_key: str, transport) -> bytes:
    """Read raw WSDL bytes from the local bundled file or the remote ?wsdl endpoint."""
    if settings.IWAY_SOAP_LOAD_LOCAL_WSDL:
        with open(_wsdl_location(service_key), "rb") as fh:
            return fh.read()
    resp = transport.session.get(_wsdl_location(service_key), timeout=settings.IWAY_SOAP_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _sanitized_wsdl_path(service_key: str, transport) -> str:
    """Write a defect-patched copy of the WSDL to a temp file and return its path.

    The live ``soap:address`` is preserved, so operation calls still hit the real
    server; only the invalid schema type is rewritten.
    """
    import tempfile

    content = _read_wsdl_bytes(service_key, transport)
    for bad, good in _WSDL_SANITIZE:
        content = content.replace(bad, good)

    fd, path = tempfile.mkstemp(prefix=f"iway_{service_key}_", suffix=".wsdl.xml")
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    _temp_wsdl_paths.append(path)
    return path


@lru_cache(maxsize=None)
def _get_client(service_key: str):
    """Lazily build (and cache) a zeep Client for the given service.

    zeep is imported here (not at module load) so the dependency is only required
    when IWAY_USE_REAL_API is enabled. WSDL parsing happens once per service.
    """
    from requests import Session
    from requests.auth import HTTPBasicAuth
    from zeep import Client, Settings
    from zeep.transports import Transport

    session = Session()
    session.auth = HTTPBasicAuth(settings.IWAY_SOAP_USER, settings.IWAY_SOAP_PASSWORD)
    transport = Transport(
        session=session,
        timeout=settings.IWAY_SOAP_TIMEOUT,
        # (connect, read) tuple — passed through to requests. A short connect
        # timeout means an unreachable ERP fails in ~5s per attempt instead of
        # 15s, so the user gets the honest-degradation answer quickly.
        operation_timeout=(settings.IWAY_SOAP_CONNECT_TIMEOUT, settings.IWAY_SOAP_TIMEOUT),
    )

    wsdl_path = _sanitized_wsdl_path(service_key, transport)
    logger.info(f"🧼 Building zeep client [{service_key}] from {wsdl_path}")
    zeep_settings = Settings(strict=False, xml_huge_tree=True)
    return Client(wsdl_path, transport=transport, settings=zeep_settings)


def _cleanup_temp_wsdls() -> None:
    for p in _temp_wsdl_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    _temp_wsdl_paths.clear()


def reset_soap_clients() -> None:
    """Clear cached zeep clients + temp WSDLs (e.g. after a config change). Test helper."""
    _get_client.cache_clear()
    _cleanup_temp_wsdls()


async def close_soap_clients() -> None:
    """Release cached clients/sessions on shutdown (lifespan symmetry)."""
    try:
        _get_client.cache_clear()
        _cleanup_temp_wsdls()
        logger.info("🔌 I-Way SOAP clients closed.")
    except Exception:  # pragma: no cover - shutdown best-effort
        pass


# ──────────────────────────────────────────────────────────────
# Low-level call helper — runs a sync zeep op in a thread, guarded
# by the api_circuit breaker + retry/backoff.
# ──────────────────────────────────────────────────────────────
async def _call(service_key: str, operation: str, _retries: int = 2, **kwargs) -> Any:
    """Invoke a SOAP operation off the event loop, with resilience.

    Raises on failure (after retries / open circuit). Callers decide whether to
    fall back to mock data.

    ``_retries``: READS may retry (idempotent). WRITES must pass ``_retries=1`` —
    a client-side timeout after a server-side success would otherwise re-fire the
    write and create duplicates (e.g. two réclamations for one request).
    """
    def _sync_call():
        client = _get_client(service_key)
        op = getattr(client.service, operation)
        return op(**kwargs)

    async def _runner():
        return await anyio.to_thread.run_sync(_sync_call)

    async def _invoke():
        return await retry_with_backoff(
            _runner,
            max_retries=_retries,
            base_delay=0.5,
            operation_name=f"SOAP {service_key}.{operation}",
            circuit=api_circuit,
        )

    if _soap_tracer is None:
        return await _invoke()

    with _soap_tracer.start_as_current_span(
        f"soap.{service_key}.{operation}",
        attributes={
            "soap.service": service_key,
            "soap.operation": operation,
            "soap.max_retries": _retries,
        },
    ) as span:
        try:
            return await _invoke()
        except Exception as e:
            span.set_status(_OtelStatus(_OtelStatusCode.ERROR))
            span.record_exception(e)
            raise


# ──────────────────────────────────────────────────────────────
# Mapping helpers — verbose Axis2 DTOs → compact display dicts.
# zeep returns object trees; serialize_object() turns them into
# plain dicts/lists so we can pluck fields defensively.
# ──────────────────────────────────────────────────────────────
def _to_dict(obj: Any) -> Any:
    """Recursively convert a zeep object tree to plain Python (dict/list/scalars).

    Already-plain inputs (dict/list/scalars) are returned untouched so the mappers
    are testable without importing zeep.
    """
    if obj is None or isinstance(obj, (dict, list, str, int, float, bool)):
        return obj
    try:
        from zeep.helpers import serialize_object
        return serialize_object(obj, target_cls=dict)
    except Exception:
        return obj


def _ref_label(value: Any) -> Optional[str]:
    """Extract a human label from a TableReferentielDto-like value.

    These reference entries usually carry ``libelle`` (+ ``code``). Falls back to
    the code or a plain string.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("libelle") or value.get("libelleFr") or value.get("code")
    return str(value)


def _g(d: Any, *keys) -> Any:
    """Safe nested get: first present key on a dict, else None."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if d.get(k) is not None:
            return d.get(k)
    return None


def _map_contrat(dto: Any) -> dict:
    """ContratAdherentWsDto → compact contract dict."""
    d = _to_dict(dto) or {}
    person = _g(d, "personnePhysique", "personnePhysiqueDto") or {}
    return {
        "num_contrat": _g(d, "numContrat"),
        "date_effet": str(_g(d, "dateEffet")) if _g(d, "dateEffet") else None,
        "date_fin_effet": str(_g(d, "dateFinEffet")) if _g(d, "dateFinEffet") else None,
        "date_resiliation": str(_g(d, "dateResiliation")) if _g(d, "dateResiliation") else None,
        "qualite": _ref_label(_g(d, "qualite")),
        "situation": _ref_label(_g(d, "situation")),
        "type_remboursement": _ref_label(_g(d, "typeRemboursement")),
        "vip": _g(d, "vip"),
        "titulaire": _g(person, "nomComplet", "nomAdherent") if isinstance(person, dict) else None,
        "num_police": _g(person, "numeroPolice") if isinstance(person, dict) else None,
    }


def _map_beneficiaire(dto: Any) -> dict:
    """PersonnePhysiqueDto → compact beneficiary dict."""
    d = _to_dict(dto) or {}
    return {
        "nom": _g(d, "nom"),
        "prenom": _g(d, "prenom"),
        "nom_complet": _g(d, "nomComplet"),
        "date_naissance": _g(d, "dateNaiss") or (str(_g(d, "dateNaissance")) if _g(d, "dateNaissance") else None),
        "age": _g(d, "age"),
        "lien": _ref_label(_g(d, "codeCntr")),
        "matricule": _g(d, "matricule"),
        "couverture_active": _g(d, "enRegle"),
        "montant_disponible": _g(d, "montantDisponible"),
    }


# Structural/financial fields safe to forward from the UNTYPED reimbursement
# rows. Whitelist, not blacklist: unknown keys may carry names or other PII the
# pseudonymization shield can't recognize, so anything unmatched is DROPPED
# before the rows can reach an external LLM.
_ROW_SAFE_KEY_RE = re.compile(
    r"(dossier|reference|\bref|statut|status|date|mnt|montant|tot|taux|num|code|acte|rembours|quittance|rang|fact|nature)",
    re.IGNORECASE,
)


def _project_row(row: Any) -> Any:
    """Reduce an untyped DTO row to its whitelisted structural fields."""
    if isinstance(row, dict):
        out = {}
        for k, v in row.items():
            if not _ROW_SAFE_KEY_RE.search(str(k)):
                continue
            if isinstance(v, (dict, list)):
                v = _project_row(v)
                if not v:
                    continue
            out[k] = v
        return out
    if isinstance(row, list):
        return [p for p in (_project_row(x) for x in row) if p not in ({}, [], None)]
    return row


def _map_remboursement_list(dto: Any) -> dict:
    """SearchContextResult → compact reimbursement-list dict.

    The per-dossier rows come back loosely typed (xs:anyType) under
    ``listResultEntityObject``; the financial totals are well-typed under
    ``contextLPResult``. Rows are projected through a structural-key whitelist
    so untyped fields (which may hold names) never leave the platform.
    """
    d = _to_dict(dto) or {}
    totals = _g(d, "contextLPResult") or {}
    rows = _g(d, "listResultEntityObject") or _g(d, "listResultDto") or []
    if not isinstance(rows, list):
        rows = [rows]
    rows = [r for r in (_project_row(x) for x in rows) if r not in ({}, [], None)]
    return {
        "result_size": _g(d, "resultSize"),
        "totaux": {
            "total_rembourse": _g(totals, "mntTotalRemb"),
            "total_regle": _g(totals, "mntTotalRegler"),
            "reste_a_charge": _g(totals, "mntResteAchargeAdherent"),
            "total_rembourse_cnam": _g(totals, "mntTotalRembCnam"),
            "part_mutuelle": _g(totals, "ttMutuelle"),
        } if isinstance(totals, dict) else {},
        "dossiers": rows,
    }


def _map_dossier_detail(dto: Any) -> dict:
    """PrestationDto → compact dossier-detail dict (defensive: huge back-office DTO)."""
    d = _to_dict(dto) or {}
    adherent = _g(d, "adherent") or {}
    beneficiaire = _g(d, "beneficiaire") or {}
    return {
        "reference": _g(d, "reference", "codeRef", "num"),
        "num_dossier": _g(d, "numDossier", "numOrdre"),
        "statut": _ref_label(_g(d, "statut")),
        "date": str(_g(d, "dateCreation")) if _g(d, "dateCreation") else None,
        "commentaire": _g(d, "commentaire"),
        "actes": _g(d, "actes"),
        "adherent": _g(adherent, "nomComplet", "raisonSociale") if isinstance(adherent, dict) else None,
        "beneficiaire": _g(beneficiaire, "nomComplet", "raisonSociale") if isinstance(beneficiaire, dict) else None,
        "montant_total": _g(d, "totTtc", "mntTotal"),
        "montant_rembourse": _g(d, "totRembourse", "mntRembourse"),
    }


def _map_reclamation(dto: Any) -> dict:
    """ReclamationDto → compact complaint dict."""
    d = _to_dict(dto) or {}
    return {
        "numero": _g(d, "numeroReclamation"),
        "objet": _g(d, "objetReclamation"),
        "description": _g(d, "descreptionReclamation"),
        "date": _g(d, "formattedDate") or (str(_g(d, "dateCreation")) if _g(d, "dateCreation") else None),
        "statut": _g(d, "statutForMobile") or _ref_label(_g(d, "statut")),
        "nature": _g(d, "natureReclamation"),
        "type": _ref_label(_g(d, "typeReclamation")),
        "num_dossier": _g(d, "numDossier"),
        "reponse": _g(d, "reponseExtarnet") or _g(d, "reponse"),
    }


def _as_list(result: Any) -> list:
    """Normalize a SOAP 'return' (single obj, list, or None) into a list."""
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result]


def is_data_fault(exc: BaseException) -> bool:
    """True for a SOAP Fault — the ERP RESPONDED and rejected the request (record
    not found / invalid police), as opposed to a transport/connection error or an
    open circuit (generic Exception from retry_with_backoff). Lets auth activation
    distinguish 401 'not recognized' from 503 'service indisponible'."""
    try:
        from zeep.exceptions import Fault
    except Exception:  # pragma: no cover — zeep optional at import time
        return False
    return isinstance(exc, Fault)


def _clean(value: Any) -> Optional[str]:
    """Strip a string field; empty/whitespace-only values become None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _fold(value: Any) -> str:
    """Lowercase + strip accents, for tolerant client-side filter matching."""
    import unicodedata
    s = str(value or "").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _map_identity(dto: Any) -> dict:
    """ContratAdherentWsDto → identity fields for ACCOUNT ACTIVATION ONLY.

    Carries CIN + date de naissance — must NEVER be placed in ``system_records``
    or any payload that reaches an LLM or the chat UI. Consumed exclusively by
    routers/auth.py to verify a first-login identity claim.
    """
    d = _to_dict(dto) or {}
    person = _g(d, "personnePhysique", "personnePhysiqueDto") or {}
    if not isinstance(person, dict):
        person = {}
    dn = _g(person, "dateNaissance", "dateNaiss")
    return {
        "nom": _clean(_g(person, "nom")),
        "prenom": _clean(_g(person, "prenom")),
        "nom_complet": _clean(_g(person, "nomComplet")),
        "date_naissance": str(dn) if dn is not None else None,
        "cin": _clean(_g(person, "numeroPieceId")),
        "num_police": _clean(_g(person, "numeroPolice")),
    }


def _map_prestataire(dto: Any) -> dict:
    """PrestataireDto (searchPsWithConvTP) → compact provider dict.

    Public directory data (conventioned providers) — not personal records.
    """
    d = _to_dict(dto) or {}
    adresse = _g(d, "adresse") or {}
    if not isinstance(adresse, dict):
        adresse = {}
    tel = _clean(_g(d, "numTelFixe")) or _clean(_g(d, "numTelMobile")) or _clean(_g(d, "numTelBureau"))
    return {
        "nom": _clean(_g(d, "nom")),
        "specialite": _clean(_g(d, "specialite")),
        "secteur": _clean(_g(d, "secteurActivite")),
        "gouvernorat": _clean(_ref_label(_g(adresse, "gouvernorat"))),
        "ville": _clean(_ref_label(_g(adresse, "ville"))),
        "adresse": _clean(_g(adresse, "adresse")),
        "telephone": tel,
        # searchPsWithConvTP only returns providers under a tiers-payant convention
        "conventionne": True,
    }


def _map_plafond(dto: Any) -> dict:
    """Plafond-per-beneficiary DTO → compact dict (op faults on test data; mapped
    defensively from the documented fields montantPlafond/Consomme/Disponible)."""
    d = _to_dict(dto) or {}
    benef = _g(d, "beneficiaire", "personnePhysique") or {}
    name = _g(benef, "nomComplet", "nom") if isinstance(benef, dict) else None
    return {
        "beneficiaire": _clean(name) or _clean(_g(d, "nomBeneficiaire", "nomBenef", "nomComplet")),
        "lien": _ref_label(_g(d, "lienParental", "codeCntr")),
        "montant_plafond": _g(d, "montantPlafond", "mntPlafond", "plafond"),
        "montant_consomme": _g(d, "montantConsomme", "mntConsomme", "consomme"),
        "montant_disponible": _g(d, "montantDisponible", "mntDisponible", "disponible"),
    }


def _map_facture(dto: Any) -> dict:
    """FacturePsDto (huge, loosely populated) → compact invoice dict.

    The row goes through the ``_project_row`` whitelist FIRST so unknown keys
    (which may hold adherent/PS names) are dropped before any field is plucked.
    """
    d = _project_row(_to_dict(dto) or {})
    if not isinstance(d, dict) or not d:
        return {}
    date = _g(d, "dateFacture", "dateCreation", "dateEnvoi")
    return {
        "num_facture": _clean(_g(d, "numFacture", "reference", "refFacture", "refFact")),
        "date": str(date) if date is not None else None,
        "montant": _g(d, "mntFacture", "montantFacture", "mntTotaleRestPayer"),
        "statut": _ref_label(_g(d, "statut")) or _clean(_g(d, "etatFacture")),
        "nature": _clean(_g(d, "natureFacture", "natureActe")),
    }


# ──────────────────────────────────────────────────────────────
# Public async API — one method per business operation.
# Each returns compact, JSON-serializable Python ready for system_records.
# ──────────────────────────────────────────────────────────────
async def get_contrat_adherent(matricule: str, num_police: str = "") -> Optional[dict]:
    """Contrat — getContratAdherentByMatricule."""
    res = await _call(
        "contrat", "getContratAdherentByMatricule",
        matricule=matricule, numPolice=num_police or None,
    )
    return _map_contrat(res) if res is not None else None


async def get_beneficiaires(matricule: str, num_police: str = "") -> list[dict]:
    """Bénéficiaires — getListeBeneficiairesByMatricule (returns PersonnePhysiqueDto[]).

    ``numPolice`` is REQUIRED by the live ERP (doc §1.3) — omitting it faults.
    """
    res = await _call(
        "contrat", "getListeBeneficiairesByMatricule",
        matricule=matricule, numPolice=num_police or None,
    )
    return [_map_beneficiaire(b) for b in _as_list(res)]


async def get_list_remboursement(
    matricule: str, num_police: str = "", page: int = 0, page_size: int = 20, **filters
) -> dict:
    """Liste des remboursements — getListRemboursementByMatricule."""
    res = await _call(
        "remboursement", "getListRemboursementByMatricule",
        matricule=matricule, page=page, pageSize=page_size,
        numPolice=num_police or filters.get("num_police") or None,
        dateDebut=filters.get("date_debut") or None,
        dateFin=filters.get("date_fin") or None,
        statut=filters.get("statut") or None,
    )
    return _map_remboursement_list(res)


async def get_dossier_remboursement(num_dossier: str) -> Optional[dict]:
    """Détail du remboursement d'un dossier — getDossierRemboursementByNumDossier."""
    res = await _call(
        "remboursement", "getDossierRemboursementByNumDossier",
        numDossier=num_dossier,
    )
    return _map_dossier_detail(res) if res is not None else None


async def get_list_reclamation(
    matricule: str, num_police: str = "", page: int = 0, page_size: int = 20, **filters
) -> list[dict]:
    """Liste des réclamations — getListReclamationByMatricule (returns ReclamationDto[])."""
    res = await _call(
        "reclamation", "getListReclamationByMatricule",
        matriculeAdherent=matricule, page=page, pageSize=page_size,
        numPolice=num_police or filters.get("num_police") or None,
        dateMinRec=filters.get("date_min") or None,
        dateMaxRec=filters.get("date_max") or None,
    )
    return [_map_reclamation(r) for r in _as_list(res)]


async def get_plafonds_beneficiaires(matricule: str, num_police: str = "") -> list[dict]:
    """Plafonds/consommation par bénéficiaire — getListPlafondBeneficiairesByMatricule.

    NOTE: faults (code 3) on the current ERP test data — the test adherent has no
    bénéficiaires. Callers degrade honestly; this is the expected LAN behavior
    until I-Way provisions an adherent with bénéficiaires.
    """
    res = await _call(
        "contrat", "getListPlafondBeneficiairesByMatricule",
        matricule=matricule, numPolice=num_police or None,
    )
    return [_map_plafond(p) for p in _as_list(res)]


async def search_prestataires(
    nom: str = "",
    specialite: str = "",
    gouvernorat: str = "",
    secteur: str = "",
    num_police: str = "",
    max_results: Optional[int] = None,
) -> list[dict]:
    """Recherche de PS conventionnés tiers payant — prestatiareWS.searchPsWithConvTP.

    PUBLIC directory data (no personal records). The op can return ~1 MB with
    loose server-side filtering, so rows are refined client-side (accent-folded
    substring match on specialite/secteur and gouvernorat/ville) and capped to
    ``PROVIDER_SEARCH_MAX_RESULTS``. The refinement only applies when it keeps at
    least one row — if our string matching is too strict, we trust the
    server-filtered result instead of returning nothing.
    """
    res = await _call(
        "prestataire_search", "searchPsWithConvTP",
        nom=nom or None,
        secteurActivite=secteur or None,
        specialite=specialite or None,
        gouvernorat=gouvernorat or None,
        numPolice=num_police or None,
    )
    rows = [_map_prestataire(p) for p in _as_list(res)]
    rows = [r for r in rows if r.get("nom")]
    if specialite:
        want = _fold(specialite)
        kept = [r for r in rows if want in _fold(r.get("specialite")) or want in _fold(r.get("secteur"))]
        rows = kept or rows
    if gouvernorat:
        want = _fold(gouvernorat)
        kept = [r for r in rows if want in _fold(r.get("gouvernorat")) or want in _fold(r.get("ville"))]
        rows = kept or rows
    cap = max_results or settings.PROVIDER_SEARCH_MAX_RESULTS
    return rows[:cap]


async def get_secteurs_activite() -> list[dict]:
    """Secteurs d'activité PS — rechercheSpecialiteWS.getListSecteurActivitesPS."""
    res = await _call("recherche_specialite", "getListSecteurActivitesPS")
    out = []
    for s in _as_list(res):
        d = _to_dict(s) or {}
        label = _clean(_g(d, "libelle", "designation"))
        if label:
            out.append({"id": _g(d, "id"), "libelle": label})
    return out


async def get_specialites_by_secteur(id_secteur: int) -> list[dict]:
    """Spécialités d'un secteur — rechercheSpecialiteWS.getListSpecialiteBySecteurActivite."""
    res = await _call(
        "recherche_specialite", "getListSpecialiteBySecteurActivite",
        idSecteurActivite=id_secteur,
    )
    out = []
    for s in _as_list(res):
        d = _to_dict(s) or {}
        label = _clean(_g(d, "libelle", "designation"))
        if label:
            out.append({"id": _g(d, "id"), "libelle": label})
    return out


async def get_villes_gouvernorats() -> list[dict]:
    """Villes par gouvernorat — rechercheSpecialiteWS.getListVilleAndGouvernorat.

    ~1.8 MB live; callers cache the mapped result (see services/referentials.py).
    Returns [{"gouvernorat": str, "villes": [str, ...]}, ...].
    """
    res = await _call("recherche_specialite", "getListVilleAndGouvernorat")
    out = []
    for entry in _as_list(res):
        d = _to_dict(entry) or {}
        gouv = _clean(_ref_label(_g(d, "parent")))
        children = _g(d, "listChild") or []
        if not isinstance(children, list):
            children = [children]
        villes = [v for v in (_clean(_ref_label(c)) for c in children) if v]
        if gouv:
            out.append({"gouvernorat": gouv, "villes": villes})
    return out


async def search_factures_adherent(
    matricule: str, num_police: str = "", page: int = 0, page_size: int = 10
) -> dict:
    """Factures adhérent — factureWS.searchFacture (returns SearchFacturePsWsDto)."""
    res = await _call(
        "facture", "searchFacture",
        matriculeAdh=matricule, numPolice=num_police or None,
        page=page, pageSize=page_size,
    )
    d = _to_dict(res) or {}
    rows = _g(d, "facturePs", "factures") or []
    if not isinstance(rows, list):
        rows = [rows]
    factures = [
        f for f in (_map_facture(x) for x in rows)
        if f.get("num_facture") or f.get("montant") or f.get("date")
    ]
    return {"result_size": _g(d, "nbrTotal", "resultSize"), "factures": factures}


async def search_factures_ps(id_tiers: str, page: int = 0, page_size: int = 10) -> dict:
    """Factures d'un prestataire — facturePsWS.searchListFactureByPs (FacturePsDto[])."""
    res = await _call(
        "facture_ps", "searchListFactureByPs",
        idTiers=int(id_tiers), page=page, pageSize=page_size,
    )
    factures = [
        f for f in (_map_facture(x) for x in _as_list(res))
        if f.get("num_facture") or f.get("montant") or f.get("date")
    ]
    return {"result_size": len(factures), "factures": factures}


async def get_contrat_ps_by_matricule_fiscal(matricule_fiscal: str) -> Optional[dict]:
    """Résolution PS — contratPsWS.getContratPsByMatriculeFiscal → {"id_tiers": str}.

    The live op returns the bare idTiers (e.g. "151537"). AUTH-ONLY usage.
    """
    res = await _call(
        "contrat_ps", "getContratPsByMatriculeFiscal",
        matriculeFiscal=matricule_fiscal,
    )
    if res is None:
        return None
    id_tiers = _clean(res if isinstance(res, str) else _g(_to_dict(res) or {}, "idTiers", "id") or str(res))
    return {"id_tiers": id_tiers} if id_tiers else None


async def get_contrat_ps_by_id_tiers(id_tiers: str) -> Optional[dict]:
    """Identité PS — contratPsWS.getContratPsByIdTiers (ContratPsDto, ~42 KB).

    AUTH-ONLY usage (activation verification). Maps just the identity fields.
    """
    res = await _call("contrat_ps", "getContratPsByIdTiers", idTiers=int(id_tiers))
    if res is None:
        return None
    d = _to_dict(res) or {}
    # the name lives on nested infCompPmDto/personneMorale shapes depending on the
    # PS type — walk the candidates defensively
    raison = None
    for key in ("infCompPmDto", "personneMorale", "tiers"):
        sub = _g(d, key)
        if isinstance(sub, dict):
            raison = _clean(_g(sub, "raisonSociale", "nomContact", "nomComplet"))
            if raison:
                break
    raison = raison or _clean(_g(d, "raisonSociale", "nomContact"))
    return {
        "id_contrat": _g(d, "idContrat"),
        "raison_sociale": raison,
        "code_cnam": _clean(_g(d, "codeCnam")),
        "matricule_fiscal": _clean(_g(d, "idFiscal", "matriculeFiscal")),
    }


# ──────────────────────────────────────────────────────────────
# Write operations (outward-facing — gated by IWAY_USE_REAL_API and by an
# explicit user action upstream; callers handle confirmation + fallback).
# ──────────────────────────────────────────────────────────────
async def create_reclamation(
    matricule: str,
    titre: str,
    description: str,
    num_police: str = "",
    nature: str = "",
    type_reclamation: str = "",
) -> Optional[dict]:
    """Create a réclamation — reclamationWS.createReclamation.

    Text-only (no attachment). Returns the created ReclamationDto mapped to the
    compact shape (its `numero` is the I-Way reference). Optional file/entity
    fields are omitted.
    """
    res = await _call(
        "reclamation", "createReclamation",
        _retries=1,  # non-idempotent write — never retry
        matriculeAdherent=matricule,
        titre=titre,
        description=description,
        numPolice=num_police or None,
        nature=nature or None,
        typeReclamation=type_reclamation or None,
    )
    return _map_reclamation(res) if res is not None else None


async def create_bs_digital(
    matricule: str,
    police: str = "",
    rang: str = "",
    reference_bs: str = "",
    files: Optional[list] = None,
) -> Optional[str]:
    """Submit a digital bordereau de soins — remboursementAdherentWS.createBsDigital.

    Returns the server's reference string. NOTE: a meaningful BS submission needs
    scanned supporting documents (`files`: FilesDto[]), which depend on the
    not-yet-built file-upload/OCR feature — so this is NOT wired into the chat
    flow yet. The client method exists so the write surface is complete/testable.
    """
    res = await _call(
        "remboursement", "createBsDigital",
        _retries=1,  # non-idempotent write — never retry
        matricule=matricule,
        police=police or None,
        rang=rang or None,
        referenceBs=reference_bs or None,
        files=files or None,
    )
    return res if isinstance(res, str) else (str(res) if res is not None else None)
