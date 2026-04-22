"""
Database Lookup Nodes — Dossier, Beneficiary, and Action Router.

These nodes access the user's personal records from the database.
Grouped together because they share the DB-tool pattern.

TODO (Phase 4): Replace mock data with real iway_client calls.
"""

import logging

from langchain_core.messages import SystemMessage

from state import ClaimsGraphState
from backend.domain.graph.llm_factory import llm

logger = logging.getLogger("I-Way-Twin")


ACTION_ROUTER_PROMPT = """Tu es un routeur pour un systeme d'assurance medicale.

L'utilisateur veut acceder a ses donnees personnelles. Classifie sa demande:

1. "dossier" -- Il veut voir ses dossiers, remboursements, reclamations, historique de soins, ou le statut d'un remboursement.
   Exemples: "Mes dossiers", "Mon remboursement", "Historique de soins", "Statut de ma reclamation"

2. "beneficiaire" -- Il veut voir les personnes couvertes par son contrat (famille, conjoints, enfants, ayants droit).
   Exemples: "Qui est sur mon contrat ?", "Mes beneficiaires", "Ma famille est-elle couverte ?"

Reponds UNIQUEMENT avec: dossier ou beneficiaire"""


async def action_router_node(state: ClaimsGraphState) -> dict:
    """
    Action Router: LLM-powered sub-classifier for PERSONAL_LOOKUP.

    Reads the user's message and decides whether to route to the
    dossier lookup or beneficiary lookup DB tool. Stores the decision
    in state so the conditional edge can read it.
    """
    last_message = state["messages"][-1]

    response = await llm.ainvoke([
        SystemMessage(content=ACTION_ROUTER_PROMPT),
        last_message,
    ])

    raw = response.content.strip().lower().replace('"', '').replace("'", "")
    # Default to dossier if ambiguous
    action = "dossier" if "dossier" in raw else ("beneficiaire" if "beneficiaire" in raw else "dossier")

    logger.info(f"Action router decided: {action} (raw: '{raw}')")
    return {"intent": state.get("intent")}  # pass-through, routing done by edge function


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
