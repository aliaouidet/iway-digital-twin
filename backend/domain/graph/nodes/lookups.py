"""
Database Lookup Nodes — Dossier, Beneficiary, and Action Router.

These nodes access the user's personal records from the database.
Grouped together because they share the DB-tool pattern.

TODO (Phase 4): Replace mock data with real iway_client calls.
"""

import logging

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


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

    Fetches the user's active claims/dossiers from the database.
    Uses the matricule from state (injected at session start, never
    sent to the LLM) to query the user's records.

    TODO (Phase 4): Replace mock with real iway_client.get_personal_dossiers()
    """
    matricule = state.get("matricule", "unknown")

    logger.info(f"Dossier lookup for matricule: {matricule}")

    # ── Mock database response ──
    mock_dossiers = {
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

    logger.info(f"Dossier lookup returned {len(mock_dossiers['dossiers'])} records")

    return {
        "system_records": mock_dossiers,
    }


async def beneficiary_lookup_node(state: ClaimsGraphState) -> dict:
    """
    Node 2d: Beneficiary Lookup.

    Fetches the user's family members/dependents on the insurance
    policy. Uses the matricule from state.

    TODO (Phase 4): Replace mock with real iway_client.get_beneficiaires_info()
    """
    matricule = state.get("matricule", "unknown")

    logger.info(f"Beneficiary lookup for matricule: {matricule}")

    # ── Mock database response ──
    mock_beneficiaries = {
        "beneficiaires": [
            {
                "nom": "Ahmed Tounsi",
                "lien": "titulaire",
                "date_naissance": "1985-06-12",
                "couverture_active": True,
            },
            {
                "nom": "Fatma Tounsi",
                "lien": "conjoint",
                "date_naissance": "1988-03-22",
                "couverture_active": True,
            },
            {
                "nom": "Youssef Tounsi",
                "lien": "enfant",
                "date_naissance": "2015-11-05",
                "couverture_active": True,
            },
        ],
        "nombre_beneficiaires": 3,
    }

    logger.info(f"Beneficiary lookup returned {len(mock_beneficiaries['beneficiaires'])} members")

    return {
        "system_records": mock_beneficiaries,
    }
