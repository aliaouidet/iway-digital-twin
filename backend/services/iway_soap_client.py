"""
I-Way SOAP Client — Async wrapper over the real I-Way Axis2 web services.

The production I-Way ERP exposes Apache Axis2 SOAP services (document/literal),
not REST. This module wraps four of them and maps their verbose DTOs down to the
compact ``system_records`` dicts the graph already consumes
(see backend/domain/graph/nodes/draft_response.py).

Services / operations used (MVP scope):
  - contratAdherentWSMeg   → getContratAdherentByMatricule        (Contrat)
                             getListeBeneficiairesByMatricule     (Bénéficiaires)
  - remboursementAdherentWS→ getListRemboursementByMatricule      (Liste remboursements)
                             getDossierRemboursementByNumDossier  (Détail dossier)
  - reclamationWS          → getListReclamationByMatricule        (Liste réclamations)

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


# ──────────────────────────────────────────────────────────────
# WSDL filenames per service (bundled in IWAY_SOAP_WSDL_DIR)
# ──────────────────────────────────────────────────────────────
_WSDL_FILES = {
    "contrat": "contratAdherentWSMeg.xml",
    "remboursement": "remboursementAdherentWS.xml",
    "reclamation": "reclamationWS.xml",
    "contrat_ps": "contratPsWS.xml",
}

# Remote ?wsdl URLs (used when IWAY_SOAP_LOAD_LOCAL_WSDL=false, i.e. on-site)
_WSDL_REMOTE = {
    "contrat": "/contratAdherentWSMeg?wsdl",
    "remboursement": "/remboursementAdherentWS?wsdl",
    "reclamation": "/reclamationWS?wsdl",
    "contrat_ps": "/contratPsWS?wsdl",
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

    return await retry_with_backoff(
        _runner,
        max_retries=_retries,
        base_delay=0.5,
        operation_name=f"SOAP {service_key}.{operation}",
        circuit=api_circuit,
    )


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
    r"(dossier|reference|\bref|statut|status|date|mnt|montant|tot|taux|num|code|acte|rembours|quittance|rang)",
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


async def get_beneficiaires(matricule: str) -> list[dict]:
    """Bénéficiaires — getListeBeneficiairesByMatricule (returns PersonnePhysiqueDto[])."""
    res = await _call(
        "contrat", "getListeBeneficiairesByMatricule",
        matricule=matricule,
    )
    return [_map_beneficiaire(b) for b in _as_list(res)]


async def get_list_remboursement(
    matricule: str, page: int = 0, page_size: int = 20, **filters
) -> dict:
    """Liste des remboursements — getListRemboursementByMatricule."""
    res = await _call(
        "remboursement", "getListRemboursementByMatricule",
        matricule=matricule, page=page, pageSize=page_size,
        numPolice=filters.get("num_police") or None,
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
    matricule: str, page: int = 0, page_size: int = 20, **filters
) -> list[dict]:
    """Liste des réclamations — getListReclamationByMatricule (returns ReclamationDto[])."""
    res = await _call(
        "reclamation", "getListReclamationByMatricule",
        matriculeAdherent=matricule, page=page, pageSize=page_size,
        numPolice=filters.get("num_police") or None,
        dateMinRec=filters.get("date_min") or None,
        dateMaxRec=filters.get("date_max") or None,
    )
    return [_map_reclamation(r) for r in _as_list(res)]


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
