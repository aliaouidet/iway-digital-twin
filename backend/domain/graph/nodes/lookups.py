"""
Database Lookup Nodes — Dossier, Beneficiary, and Action Router.

These nodes access the user's personal records. When IWAY_USE_REAL_API is true
they call the real I-Way SOAP services (backend/services/iway_soap_client.py);
otherwise — or if a SOAP call fails — they fall back to mock data so the
conversation degrades gracefully rather than breaking (QR3).
"""

import asyncio
import logging

from state import ClaimsGraphState
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


def _service_unavailable(kind: str) -> dict:
    """Real-mode degradation record: an honest notice, NEVER fabricated data.

    When IWAY_USE_REAL_API is on, a SOAP failure must not fall back to the demo
    mocks — that would present invented dossiers/amounts as the user's own
    records with high confidence. This shell contains no rows, so the db
    confidence signal stays off; in practice the LLM confidently RELAYS the
    notice (auto-respond, observed ~0.95) — the message itself invites the user
    to retry or ask for an agent, which avoids flooding the agent queue with
    auto-handoffs during an ERP outage.
    """
    return {
        "service_indisponible": True,
        "message": (
            f"Les {kind} ne sont pas accessibles pour le moment "
            "(service I-Way temporairement indisponible). Veuillez réessayer "
            "dans quelques instants ou demander un agent."
        ),
    }


# ── Mock data (used ONLY when IWAY_USE_REAL_API is false — demo/dev mode) ──

def _mock_dossiers() -> dict:
    return {
        "dossiers": [
            {
                "id": "DOS-2026-0042",
                "type": "consultation",
                "status": "rembourse",
                "montant": 180.0,
                "date_soins": "2026-03-15",
                "prestataire": "Dr. Mehdi Ben Salah",
                "montant_rembourse": 126.0,
                "taux_remboursement": 70,
            },
            {
                "id": "DOS-2026-0067",
                "type": "analyses",
                "status": "en_cours",
                "montant": 95.0,
                "date_soins": "2026-04-02",
                "prestataire": "Laboratoire Central Tunis",
                "montant_rembourse": None,
                "taux_remboursement": None,
            },
        ],
        "total_rembourse_2026": 1245.0,
        "plafond_annuel": 5000.0,
    }


def _mock_beneficiaries() -> dict:
    return {
        "beneficiaires": [
            {"nom": "Ahmed Tounsi", "lien": "titulaire", "date_naissance": "1985-06-12", "couverture_active": True},
            {"nom": "Fatma Tounsi", "lien": "conjoint", "date_naissance": "1988-03-22", "couverture_active": True},
            {"nom": "Youssef Tounsi", "lien": "enfant", "date_naissance": "2015-11-05", "couverture_active": True},
        ],
        "nombre_beneficiaires": 3,
    }


def _mock_reclamations() -> dict:
    return {
        "reclamations": [
            {"numero": "REC-2026-001", "objet": "Remboursement tardif", "statut": "En cours",
             "date": "2026-03-10", "type": "Remboursement", "reponse": None},
            {"numero": "REC-2025-114", "objet": "Carte non reçue", "statut": "Clôturé",
             "date": "2025-12-01", "type": "Administratif", "reponse": "Duplicata envoyé le 05/12/2025"},
        ],
        "nombre_reclamations": 2,
    }


def _mock_dossier_detail(num_dossier: str | None) -> dict:
    return {
        "dossier_detail": {
            "num_dossier": num_dossier or "DOS-2026-0042",
            "statut": "rembourse",
            "date": "2026-03-15",
            "beneficiaire": "Ahmed Tounsi",
            "actes": ["Consultation généraliste"],
            "montant_total": 180.0,
            "montant_rembourse": 126.0,
            "taux_remboursement": 70,
        }
    }


async def action_router_node(state: ClaimsGraphState) -> dict:
    """
    Action Router: Deterministic pass-through for PERSONAL_LOOKUP.

    Routing is handled entirely by the `route_action` conditional edge
    using keyword matching (zero-latency, no LLM call required).
    This node exists as a topology anchor for the conditional edge.
    """
    logger.info("Action router pass-through (routing delegated to edge function)")
    return {"intent": state.get("intent")}


async def dossier_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2c: Dossier Lookup.

    Fetches the user's contract + reimbursement dossiers. Uses the matricule
    from state (injected at session start, never sent to the LLM).

    Real path (IWAY_USE_REAL_API): contratAdherentWSMeg.getContratAdherentByMatricule
    + remboursementAdherentWS.getListRemboursementByMatricule. Falls back to mock
    on any error.
    """
    matricule = state.get("matricule", "unknown")
    logger.info(f"Dossier lookup for matricule: {matricule}")

    if settings.IWAY_USE_REAL_API:
        try:
            from backend.services import iway_soap_client as soap

            # Two independent SOAP calls — run them concurrently to stay within
            # the latency budget. return_exceptions=True so one failure doesn't
            # orphan the sibling call: a single failure degrades to a partial
            # result; only a double failure falls back to mock.
            contrat, remboursements = await asyncio.gather(
                soap.get_contrat_adherent(matricule),
                soap.get_list_remboursement(matricule),
                return_exceptions=True,
            )
            if isinstance(contrat, BaseException) and isinstance(remboursements, BaseException):
                raise contrat  # both failed → mock fallback below
            if isinstance(contrat, BaseException):
                logger.warning(f"⚠️ Contrat fetch failed ({contrat}); continuing with remboursements only")
                contrat = None
            if isinstance(remboursements, BaseException):
                logger.warning(f"⚠️ Remboursements fetch failed ({remboursements}); continuing with contrat only")
                remboursements = None

            records = {
                "contrat": contrat,
                "remboursements": remboursements,
                # "dossiers" key kept so draft_response_node detects DB data
                "dossiers": (remboursements or {}).get("dossiers", []),
            }
            logger.info(
                f"Dossier lookup (real API) ok — "
                f"{len(records['dossiers'])} dossier(s), contrat={'yes' if contrat else 'no'}"
            )
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real dossier lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable("dossiers de remboursement")}

    mock = _mock_dossiers()
    logger.info(f"Dossier lookup returned {len(mock['dossiers'])} records (mock)")
    return {"system_records": mock}


async def beneficiary_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2d: Beneficiary Lookup.

    Fetches the family members/dependents on the policy.

    Real path (IWAY_USE_REAL_API): contratAdherentWSMeg.getListeBeneficiairesByMatricule.
    Falls back to mock on any error.
    """
    matricule = state.get("matricule", "unknown")
    logger.info(f"Beneficiary lookup for matricule: {matricule}")

    if settings.IWAY_USE_REAL_API:
        try:
            from backend.services import iway_soap_client as soap

            beneficiaires = await soap.get_beneficiaires(matricule)
            records = {
                "beneficiaires": beneficiaires,
                "nombre_beneficiaires": len(beneficiaires),
            }
            logger.info(f"Beneficiary lookup (real API) ok — {len(beneficiaires)} member(s)")
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real beneficiary lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable("informations bénéficiaires")}

    mock = _mock_beneficiaries()
    logger.info(f"Beneficiary lookup returned {len(mock['beneficiaires'])} members (mock)")
    return {"system_records": mock}


async def reclamation_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2e: Réclamation Lookup.

    Lists the user's complaints/claims.

    Real path (IWAY_USE_REAL_API): reclamationWS.getListReclamationByMatricule.
    Falls back to mock on any error.
    """
    matricule = state.get("matricule", "unknown")
    logger.info(f"Reclamation lookup for matricule: {matricule}")

    if settings.IWAY_USE_REAL_API:
        try:
            from backend.services import iway_soap_client as soap

            reclamations = await soap.get_list_reclamation(matricule)
            records = {
                "reclamations": reclamations,
                "nombre_reclamations": len(reclamations),
            }
            logger.info(f"Reclamation lookup (real API) ok — {len(reclamations)} item(s)")
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real reclamation lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable("réclamations")}

    mock = _mock_reclamations()
    logger.info(f"Reclamation lookup returned {len(mock['reclamations'])} items (mock)")
    return {"system_records": mock}


async def dossier_detail_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2f: Reimbursement Dossier Detail.

    Surfaces ONE specific reimbursement dossier. The dossier number is parsed
    from the user's message (e.g. "détail du dossier DOS-2026-0042").

    Real path (IWAY_USE_REAL_API): remboursementAdherentWS.getDossierRemboursementByNumDossier.
    Falls back to mock on any error or when no number can be parsed.
    """
    from backend.domain.graph.routing import extract_dossier_number

    matricule = state.get("matricule", "unknown")
    num_dossier = extract_dossier_number(state["messages"][-1].content)
    logger.info(f"Dossier detail lookup for matricule={matricule}, num_dossier={num_dossier}")

    if settings.IWAY_USE_REAL_API:
        if not num_dossier:
            # Real mode must not fabricate a detail for a missing/unparsable
            # number — ask for it instead (low confidence → clarification).
            return {"system_records": {
                "dossier_detail": None,
                "precision_requise": "Le numéro du dossier est nécessaire pour consulter son détail.",
            }}
        try:
            from backend.services import iway_soap_client as soap

            detail = await soap.get_dossier_remboursement(num_dossier)
            records = {"dossier_detail": detail, "num_dossier": num_dossier}
            logger.info(f"Dossier detail lookup (real API) ok — {num_dossier}")
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real dossier detail lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable(f"détails du dossier {num_dossier}")}

    mock = _mock_dossier_detail(num_dossier)
    logger.info(f"Dossier detail lookup returned mock for {mock['dossier_detail']['num_dossier']}")
    return {"system_records": mock}
