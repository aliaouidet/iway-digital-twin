"""
Database Lookup Nodes — Dossier, Beneficiary, and Action Router.

These nodes access the user's personal records. When IWAY_USE_REAL_API is true
they call the real I-Way SOAP services (backend/services/iway_soap_client.py);
otherwise — or if a SOAP call fails — they fall back to mock data so the
conversation degrades gracefully rather than breaking (QR3).
"""

import asyncio
import logging

from backend.domain.state import ClaimsGraphState
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
            {"nom": "Ahmed Tounsi", "lien": "titulaire", "date_naissance": "12/06/1985", "couverture_active": True},
            {"nom": "Fatma Tounsi", "lien": "conjoint", "date_naissance": "22/03/1988", "couverture_active": True},
            {"nom": "Youssef Tounsi", "lien": "enfant", "date_naissance": "05/11/2015", "couverture_active": True},
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


def _mock_plafonds() -> dict:
    # Consistent with _mock_dossiers (plafond 5000 / consommé 1245) and the
    # _mock_beneficiaries family.
    return {
        "plafonds": [
            {"beneficiaire": "Ahmed Tounsi", "lien": "titulaire",
             "montant_plafond": 5000.0, "montant_consomme": 1245.0, "montant_disponible": 3755.0},
            {"beneficiaire": "Fatma Tounsi", "lien": "conjoint",
             "montant_plafond": 3000.0, "montant_consomme": 410.0, "montant_disponible": 2590.0},
            {"beneficiaire": "Youssef Tounsi", "lien": "enfant",
             "montant_plafond": 2000.0, "montant_consomme": 180.0, "montant_disponible": 1820.0},
        ],
        "nombre_beneficiaires": 3,
    }


def _mock_factures(role: str) -> dict:
    if role == "Prestataire":
        return {
            "factures": [
                {"num_facture": "FACT-2026-0231", "date": "2026-04-22", "montant": 1840.0,
                 "statut": "En cours de traitement", "nature": "Facture bordereau"},
                {"num_facture": "FACT-2026-0198", "date": "2026-03-30", "montant": 2620.0,
                 "statut": "Réglée", "nature": "Facture tiers payant"},
            ],
            "result_size": 2,
            "role_vue": "prestataire",
        }
    return {
        "factures": [
            {"num_facture": "FA-2026-0412", "date": "2026-04-10", "montant": 95.0,
             "statut": "En cours", "nature": "Analyses"},
            {"num_facture": "FA-2026-0388", "date": "2026-03-15", "montant": 180.0,
             "statut": "Remboursée", "nature": "Consultation"},
        ],
        "result_size": 2,
        "role_vue": "adherent",
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
            num_police = state.get("num_police", "")
            contrat, remboursements = await asyncio.gather(
                soap.get_contrat_adherent(matricule, num_police),
                soap.get_list_remboursement(matricule, num_police),
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

            # Normalize onto the canonical shape (the same one the mock emits and
            # the chat claim-cards render) — raw _project_row rows keep SOAP key
            # names (numDossier/mnt*/statut) that neither the cards nor the LLM
            # prompt should have to guess at.
            from backend.services.agent_assist import norm_real_contrat, norm_real_dossier_row
            totaux = (remboursements or {}).get("totaux") or {}
            records = {
                "contrat": norm_real_contrat(contrat, totaux),
                "remboursements": remboursements,
                # "dossiers" key kept so draft_response_node detects DB data
                "dossiers": [
                    norm_real_dossier_row(r)
                    for r in (remboursements or {}).get("dossiers", [])
                ],
                "total_rembourse_2026": totaux.get("total_rembourse"),
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

            beneficiaires = await soap.get_beneficiaires(matricule, state.get("num_police", ""))
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

            reclamations = await soap.get_list_reclamation(matricule, state.get("num_police", ""))
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


async def plafond_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2g: Plafond / Consommation Lookup.

    Per-beneficiary annual ceiling, consumed and remaining amounts.

    Real path (IWAY_USE_REAL_API): contratAdherentWSMeg.getListPlafondBeneficiairesByMatricule.
    NOTE: the op faults on the current ERP test data (the test adherent has no
    bénéficiaires) — the honest-degradation answer IS the expected live behavior
    until I-Way provisions richer test data.
    """
    matricule = state.get("matricule", "unknown")
    logger.info(f"Plafond lookup for matricule: {matricule}")

    if settings.IWAY_USE_REAL_API:
        try:
            from backend.services import iway_soap_client as soap

            plafonds = await soap.get_plafonds_beneficiaires(
                matricule, state.get("num_police", "")
            )
            records = {"plafonds": plafonds, "nombre_beneficiaires": len(plafonds)}
            logger.info(f"Plafond lookup (real API) ok — {len(plafonds)} bénéficiaire(s)")
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real plafond lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable("plafonds et consommation")}

    mock = _mock_plafonds()
    logger.info(f"Plafond lookup returned {len(mock['plafonds'])} rows (mock)")
    return {"system_records": mock}


async def facture_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2h: Facture Lookup (role-aware).

    Adhérents get their own invoices (factureWS.searchFacture); Prestataires get
    the invoices they submitted (facturePsWS.searchListFactureByPs via the
    id_tiers carried in state).
    """
    matricule = state.get("matricule", "unknown")
    role = state.get("role", "")
    logger.info(f"Facture lookup for matricule: {matricule} (role={role or 'Adherent'})")

    if settings.IWAY_USE_REAL_API:
        try:
            from backend.services import iway_soap_client as soap

            if role == "Prestataire" and state.get("id_tiers"):
                result = await soap.search_factures_ps(state["id_tiers"])
                records = {**result, "role_vue": "prestataire"}
            else:
                result = await soap.search_factures_adherent(
                    matricule, state.get("num_police", "")
                )
                records = {**result, "role_vue": "adherent"}
            logger.info(f"Facture lookup (real API) ok — {len(records.get('factures', []))} facture(s)")
            return {"system_records": records}
        except Exception as e:
            logger.warning(f"⚠️ Real facture lookup failed ({e}); degrading honestly")
            return {"system_records": _service_unavailable("factures")}

    mock = _mock_factures(role)
    logger.info(f"Facture lookup returned {len(mock['factures'])} rows (mock, {mock['role_vue']})")
    return {"system_records": mock}
