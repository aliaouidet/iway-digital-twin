"""
bot_tools.py — LangChain Tools for the I-Santé AI Agent.

Three async tools the LLM can invoke:
  1. get_personal_dossiers  → calls the Mock Server's protected /dossiers endpoint
  2. search_knowledge_base  → FAISS semantic search on insurance rules
  3. escalate_to_human      → creates an escalation ticket via the Mock Server

Security: token and matricule are annotated with InjectedToolArg so they are
HIDDEN from the LLM's tool schema. The custom tool_executor in agent.py injects
them from AgentState at runtime.
"""

import os
from typing import Annotated
import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool, InjectedToolArg

load_dotenv()

MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://localhost:8000")


# ── Tool 1: Personal Dossiers (API) ──────────────────────────

@tool
async def get_personal_dossiers(
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
    """Récupère les dossiers médicaux et administratifs d'un adhérent
    depuis le système I-Way. Utilise cette fonction quand l'utilisateur
    demande ses dossiers, contrats ou couvertures en cours."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
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
async def search_knowledge_base(query: str) -> str:
    """Recherche dans la base de connaissances des regles et politiques
    d'assurance I-Way en utilisant la recherche semantique.
    Utilise cette fonction pour repondre aux questions sur les plafonds,
    remboursements, delais, primes et procedures."""
    try:
        from backend.services.rag_service import retrieve_context
        results = retrieve_context(query, top_k=3)

        if not results:
            return "Aucune information trouvee dans la base de connaissances."

        formatted = []
        for i, res in enumerate(results, 1):
            similarity_pct = round(res["similarity"] * 100, 1)
            metadata = res.get("metadata", {})
            question = metadata.get("question", "")
            reponse = metadata.get("reponse", res["chunk_text"])
            formatted.append(
                f"[Resultat {i} — pertinence {similarity_pct}%]\n"
                f"Q: {question}\n"
                f"R: {reponse}"
            )
        return "\n\n".join(formatted)
    except Exception as e:
        # Fallback to rag_engine if backend is not available (standalone mode)
        try:
            import rag_engine
            return rag_engine.search(query, k=3)
        except Exception:
            return f"Erreur lors de la recherche: {e}"


# ── Tool 3: Escalation to Human Agent ────────────────────────

@tool
async def escalate_to_human(
    issue_description: str,
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
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
        async with httpx.AsyncClient() as client:
            resp = await client.post(
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


# ── Tool 4: Medical Receipt OCR (Gemini Vision) ──────────────

OCR_EXTRACTION_PROMPT = """Analyse cette facture ou reçu médical et extrais les informations suivantes.
Retourne UNIQUEMENT du JSON valide, sans commentaires ni texte supplémentaire.

Format de sortie EXACT:
{
  "nom_prestataire": "Nom du médecin ou de la clinique",
  "date": "Date de la consultation (format JJ/MM/AAAA)",
  "montant_total": "Montant total en TND (nombre uniquement)",
  "acte_medical": "Type d'acte (ex: Consultation générale, Soins dentaires, Optique, Analyses, Radiologie)"
}

Si une information est illisible ou absente, mets null pour ce champ.
Si l'image n'est pas une facture médicale, retourne:
{"erreur": "L'image fournie n'est pas une facture médicale identifiable."}"""


@tool
async def analyze_medical_receipt(base64_image: str) -> str:
    """Analyse une facture ou un reçu médical à partir d'une image.
    Extrait automatiquement: le nom du prestataire, la date, le montant total,
    et le type d'acte médical. Utilise cette fonction quand l'utilisateur
    fournit une photo de facture médicale pour estimer son remboursement."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage as HMsg

        vision_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
        )

        message = HMsg(
            content=[
                {"type": "text", "text": OCR_EXTRACTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ]
        )

        response = await vision_llm.ainvoke([message])
        return response.content

    except Exception as e:
        return (
            '{"erreur": "Impossible d\'analyser l\'image. '
            f'Détail: {str(e)}"'
            '}'
        )
