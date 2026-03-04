"""
bot_tools.py — LangChain Tools for the I-Santé AI Agent.

Three tools the LLM can invoke:
  1. get_personal_dossiers  → calls the Mock Server's protected /dossiers endpoint
  2. search_knowledge_base  → simulates a RAG vector search on insurance rules
  3. escalate_to_human      → creates an escalation ticket via the Mock Server
"""

import os
import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://localhost:8000")


# ── Tool 1: Personal Dossiers (API) ──────────────────────────

@tool
def get_personal_dossiers(matricule: str, token: str) -> str:
    """Récupère les dossiers médicaux et administratifs d'un adhérent
    depuis le système I-Way. Utilise cette fonction quand l'utilisateur
    demande ses dossiers, contrats ou couvertures en cours."""
    try:
        resp = httpx.get(
            f"{MOCK_SERVER_URL}/api/v1/adherent/dossiers",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.text
        return f"Erreur API: code {resp.status_code} — {resp.text}"
    except httpx.ConnectError:
        return "Erreur: impossible de joindre le serveur I-Way. Vérifiez qu'il est démarré."
    except Exception as e:
        return f"Erreur inattendue: {e}"


# ── Tool 2: Knowledge Base / RAG ─────────────────────────────

@tool
def search_knowledge_base(query: str) -> str:
    """Recherche dans la base de connaissances des regles et politiques
    d'assurance I-Way en utilisant la recherche semantique.
    Utilise cette fonction pour repondre aux questions sur les plafonds,
    remboursements, delais, primes et procedures."""
    import rag_engine
    return rag_engine.search(query, k=3)


# ── Tool 3: Escalation to Human Agent ────────────────────────

@tool
def escalate_to_human(matricule: str, token: str, issue_description: str) -> str:
    """Transfère la conversation vers un agent humain en créant un ticket
    d'escalade. Utilise cette fonction UNIQUEMENT quand tu ne peux pas
    répondre à la question, quand l'utilisateur est mécontent, ou quand
    il demande explicitement à parler à un humain."""
    try:
        payload = {
            "matricule": matricule,
            "conversation_id": "conv-agent-auto",
            "chat_history": [
                {"role": "user", "content": issue_description},
                {"role": "assistant", "content": "Je transfère votre demande à un agent humain."},
            ],
            "reason": issue_description,
        }
        resp = httpx.post(
            f"{MOCK_SERVER_URL}/api/v1/support/escalade",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                f"Escalade réussie ! Ticket créé : {data['case_id']}. "
                f"Position dans la file : {data['queue_position']}. "
                f"Temps d'attente estimé : {data['estimated_wait']}."
            )
        return f"Erreur lors de l'escalade: code {resp.status_code} — {resp.text}"
    except httpx.ConnectError:
        return "Erreur: impossible de joindre le serveur I-Way pour l'escalade."
    except Exception as e:
        return f"Erreur inattendue lors de l'escalade: {e}"
