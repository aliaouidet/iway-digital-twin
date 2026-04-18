"""
I-Way API Client — Async HTTP client for the real I-Way insurance backend.

This module provides a clean abstraction over the I-Way REST API.
In development, endpoints are served by iway_mock.py on localhost:8000.
In production, set IWAY_API_BASE_URL to the real I-Way API server.

Usage:
    from backend.services.iway_client import IWayClient

    client = IWayClient()
    dossiers = await client.get_dossiers(token)
    kb_items = await client.get_knowledge_base(token)

Toggle: Set IWAY_USE_REAL_API=true in .env to point at the real API.
"""

import logging
from typing import List, Dict, Any, Optional

import httpx

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


# --- Shared HTTP client with connection pooling ---
_iway_client: httpx.AsyncClient | None = None


def _get_iway_client() -> httpx.AsyncClient:
    """Lazily create a shared async client for I-Way API with connection pooling."""
    global _iway_client
    if _iway_client is None or _iway_client.is_closed:
        base_url = settings.IWAY_API_BASE_URL if settings.IWAY_USE_REAL_API else settings.MOCK_SERVER_URL
        headers = {}
        if settings.IWAY_USE_REAL_API and settings.IWAY_API_KEY:
            headers["X-API-Key"] = settings.IWAY_API_KEY

        _iway_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            headers=headers,
        )
        logger.info(f"🔗 I-Way client initialized → {base_url} (real={settings.IWAY_USE_REAL_API})")
    return _iway_client


async def close_client():
    """Gracefully close the shared client (call during app shutdown)."""
    global _iway_client
    if _iway_client and not _iway_client.is_closed:
        await _iway_client.aclose()
        _iway_client = None


# ==============================================================
# KNOWLEDGE BASE
# ==============================================================

async def get_knowledge_base(token: str = "") -> List[dict]:
    """Fetch insurance rules for RAG indexing.
    
    Returns a list of {id, question, reponse, cible, tags} entries.
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/knowledge-base",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", data) if isinstance(data, dict) else data


# ==============================================================
# USER PROFILE
# ==============================================================

async def get_user_profile(token: str) -> dict:
    """Fetch authenticated user's profile info."""
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


# ==============================================================
# INSURANCE DATA ENDPOINTS
# ==============================================================

async def get_dossiers(token: str) -> List[dict]:
    """Fetch user's insurance dossiers/contracts.
    
    Returns: [{id, type, statut, date_effet, formule, prime_mensuelle, ...}]
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/adherent/dossiers",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_beneficiaires(token: str) -> List[dict]:
    """Fetch user's family beneficiaries.
    
    Returns: [{id, nom, prenom, lien, date_naissance, ...}]
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/adherent/beneficiaires",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_prestations(token: str) -> List[dict]:
    """Fetch user's medical services history.
    
    Returns: [{id, date, acte, medecin, montant, rembourse, statut}]
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/prestations",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_remboursements(token: str) -> List[dict]:
    """Fetch user's reimbursement payment history.
    
    Returns: [{id, date, montant, motif, status, rib}]
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/remboursements",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_reclamations(token: str) -> List[dict]:
    """Fetch user's complaint/claim history.
    
    Returns: [{id, date, objet, statut, resolution}]
    """
    client = _get_iway_client()
    resp = await client.get(
        "/api/v1/reclamations",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


# ==============================================================
# ESCALATION
# ==============================================================

async def escalate_to_support(
    token: str,
    matricule: str,
    chat_history: List[Dict[str, Any]],
    reason: str = "User request",
) -> dict:
    """Create an escalation ticket in the I-Way support system."""
    client = _get_iway_client()
    payload = {
        "matricule": matricule,
        "conversation_id": "conv-agent-auto",
        "chat_history": chat_history,
        "reason": reason,
    }
    resp = await client.post(
        "/api/v1/support/escalade",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()
