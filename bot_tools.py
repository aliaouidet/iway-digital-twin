"""
bot_tools.py — LangChain Tools for the I-Santé AI Agent.

Seven async tools the LLM can invoke:
  1. get_personal_dossiers   → user's insurance contracts/coverage
  2. get_beneficiaires_info  → user's family members (conjoint, enfants)
  3. get_prestations_history → user's medical services history
  4. get_remboursements_status → user's reimbursement tracking
  5. search_knowledge_base   → semantic search on insurance rules (RAG)
  6. escalate_to_human       → creates an escalation ticket
  7. analyze_medical_receipt → OCR extraction via Gemini Vision

Security: token and matricule are annotated with InjectedToolArg so they are
HIDDEN from the LLM's tool schema. The custom tool_executor in agent.py injects
them from AgentState at runtime.

Performance: All API-calling tools use the shared iway_client which provides
connection pooling via httpx.AsyncClient.
"""

import json
from typing import Annotated

from langchain_core.tools import tool, InjectedToolArg


# ── Tool 1: Personal Dossiers ────────────────────────────────

@tool
async def get_personal_dossiers(
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
    """Récupère les dossiers d'assurance et contrats de l'adhérent
    depuis le système I-Way. Utilise cette fonction quand l'utilisateur
    demande ses dossiers, contrats, formules ou couvertures en cours."""
    try:
        from backend.services.iway_client import get_dossiers
        data = await get_dossiers(token)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erreur lors de la récupération des dossiers: {e}"


# ── Tool 2: Beneficiaries Info ───────────────────────────────

@tool
async def get_beneficiaires_info(
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
    """Récupère la liste des bénéficiaires (conjoint, enfants, parents à charge)
    couverts par le contrat de l'adhérent. Utilise cette fonction quand
    l'utilisateur pose des questions sur sa famille, ses ayants droit,
    ou la couverture de ses enfants."""
    try:
        from backend.services.iway_client import get_beneficiaires
        data = await get_beneficiaires(token)
        if not data:
            return "Aucun bénéficiaire enregistré sur votre contrat."
        formatted = []
        for b in data:
            line = f"- {b.get('prenom', '')} {b.get('nom', '')} ({b.get('lien', 'N/A')})"
            if b.get('date_naissance'):
                line += f", né(e) le {b['date_naissance']}"
            if b.get('scolarise'):
                line += " (scolarisé)"
            formatted.append(line)
        return "Bénéficiaires enregistrés:\n" + "\n".join(formatted)
    except Exception as e:
        return f"Erreur lors de la récupération des bénéficiaires: {e}"


# ── Tool 3: Prestations History ──────────────────────────────

@tool
async def get_prestations_history(
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
    """Récupère l'historique des prestations médicales et actes de soins.
    Utilise cette fonction quand l'utilisateur demande ses consultations
    récentes, actes médicaux passés, ou veut savoir quel médecin il a vu."""
    try:
        from backend.services.iway_client import get_prestations
        data = await get_prestations(token)
        if not data:
            return "Aucune prestation enregistrée."
        formatted = []
        for p in data:
            line = f"- [{p.get('date', 'N/A')}] {p.get('acte', 'N/A')}"
            if p.get('medecin'):
                line += f" — {p['medecin']}"
            if p.get('montant') is not None:
                line += f" — {p['montant']} TND"
                if p.get('rembourse') is not None:
                    line += f" (remboursé: {p['rembourse']} TND)"
            line += f" — Statut: {p.get('statut', 'N/A')}"
            formatted.append(line)
        return "Historique des prestations:\n" + "\n".join(formatted)
    except Exception as e:
        return f"Erreur lors de la récupération des prestations: {e}"


# ── Tool 4: Reimbursement Status ─────────────────────────────

@tool
async def get_remboursements_status(
    matricule: Annotated[str, InjectedToolArg],
    token: Annotated[str, InjectedToolArg],
) -> str:
    """Récupère l'état des remboursements (virements effectués et en attente).
    Utilise cette fonction quand l'utilisateur demande où en est son
    remboursement, combien il a été remboursé, ou le suivi de ses virements."""
    try:
        from backend.services.iway_client import get_remboursements
        data = await get_remboursements(token)
        if not data:
            return "Aucun remboursement enregistré."
        formatted = []
        total_paid = 0
        pending = 0
        for r in data:
            status_icon = "✅" if r.get("status") == "Payé" else "⏳"
            line = f"- {status_icon} [{r.get('date', 'N/A')}] {r.get('montant', 0)} TND — {r.get('motif', 'N/A')} — {r.get('status', 'N/A')}"
            formatted.append(line)
            if r.get("status") == "Payé":
                total_paid += r.get("montant", 0)
            else:
                pending += r.get("montant", 0)
        summary = f"\n\nTotal remboursé: {total_paid} TND"
        if pending > 0:
            summary += f" | En attente: {pending} TND"
        return "Suivi des remboursements:\n" + "\n".join(formatted) + summary
    except Exception as e:
        return f"Erreur lors de la récupération des remboursements: {e}"


# ── Tool 5: Knowledge Base / RAG ─────────────────────────────

@tool
async def search_knowledge_base(query: str) -> str:
    """Recherche dans la base de connaissances des règles et politiques
    d'assurance I-Way en utilisant la recherche sémantique.
    Utilise cette fonction pour répondre aux questions sur les plafonds,
    remboursements, délais, primes et procédures."""
    try:
        from backend.services.rag_service import async_retrieve_context
        results = await async_retrieve_context(query, top_k=3)

        if not results:
            return "Aucune information trouvée dans la base de connaissances."

        formatted = []
        for i, res in enumerate(results, 1):
            similarity_pct = round(res["similarity"] * 100, 1)
            metadata = res.get("metadata", {})
            question = metadata.get("question", "")
            reponse = metadata.get("reponse", res["chunk_text"])
            formatted.append(
                f"[Résultat {i} — pertinence {similarity_pct}%]\n"
                f"Q: {question}\n"
                f"R: {reponse}"
            )
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Erreur lors de la recherche: {e}"


# ── Tool 6: Escalation to Human Agent ────────────────────────

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
        from backend.services.iway_client import escalate_to_support
        data = await escalate_to_support(
            token=token,
            matricule=matricule,
            chat_history=[
                {"role": "user", "content": issue_description},
                {"role": "assistant", "content": "Je transfère votre demande à un agent humain."},
            ],
            reason=issue_description,
        )
        return (
            f"Escalade réussie ! Ticket créé : {data.get('case_id', 'N/A')}. "
            f"Position dans la file : {data.get('queue_position', 'N/A')}. "
            f"Temps d'attente estimé : {data.get('estimated_wait', 'N/A')}."
        )
    except Exception as e:
        return f"Erreur lors de l'escalade: {e}"


# ── Tool 7: Medical Receipt OCR (Gemini Vision) ──────────────

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
