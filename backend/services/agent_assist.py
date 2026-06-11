"""
Agent Assist — business logic behind the agent workspace endpoints.

Extracted from routers/sessions.py (which had grown LLM prompt construction,
SOAP-shape normalization and topic extraction inside an HTTP router). The
router now only does HTTP/authz concerns and delegates here.

Contents:
  - Briefing summary generation (LLM + extractive fallback)
  - Co-pilot reply suggestion (RAG-grounded draft, agent reviews before send)
  - Topic extraction + conversation excerpts
  - client-context normalizers (SOAP mapper shapes → the UI's canonical shape)
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("I-Way-Twin")


# ==============================================================
# LLM (delegates to the graph's single source of model selection)
# ==============================================================

def build_assist_llm(temperature: float = 0.1):
    """Chat LLM for briefing + co-pilot — see backend/domain/graph/llm_factory.py."""
    from backend.domain.graph.llm_factory import build_llm
    return build_llm(temperature=temperature)


# ==============================================================
# BRIEFING
# ==============================================================

async def generate_briefing_summary(
    user_name: str,
    user_role: str,
    reason: str,
    conversation_excerpt: str,
) -> str:
    """Generate an LLM summary of the conversation for the agent briefing."""
    try:
        llm = build_assist_llm(temperature=0.1)

        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"""Tu es un assistant interne pour les agents du support I-Santé.
Génère un résumé concis (3-4 phrases) de cette conversation pour aider l'agent à comprendre rapidement la situation.

Client: {user_name} ({user_role})
Raison d'escalade: {reason or 'Non spécifiée'}

Conversation:
{conversation_excerpt[:3000]}

Résumé pour l'agent (en français, 3-4 phrases max):"""

        response = await asyncio.wait_for(
            llm.ainvoke([
                SystemMessage(content="Tu résumes des conversations client pour les agents de support."),
                HumanMessage(content=prompt),
            ]),
            timeout=15.0,
        )
        return response.content.strip()

    except Exception as e:
        logger.warning(f"⚠️ Briefing summary generation failed: {e}")
        return fallback_summary(user_name, user_role, reason, conversation_excerpt)


def fallback_summary(user_name: str, user_role: str, reason: str, excerpt: str) -> str:
    """Simple extractive summary when the LLM is unavailable."""
    lines = excerpt.split("\n")
    client_lines = [l for l in lines if l.startswith("Client:")]
    if client_lines:
        first_q = client_lines[0].replace("Client: ", "")
        summary = f"{user_name} ({user_role}) a contacté le support. "
        summary += f"Question initiale : \"{first_q[:100]}\". "
        if reason:
            summary += f"Escaladé car : {reason}."
        return summary
    return f"{user_name} ({user_role}) a contacté le support. Raison: {reason or 'non spécifiée'}."


# ==============================================================
# CO-PILOT SUGGESTION
# ==============================================================

async def generate_reply_suggestion(
    query: str,
    kb_context: str,
    conversation_excerpt: str,
    instruction: Optional[str] = None,
) -> str:
    """Draft a candidate reply for the agent, grounded in the knowledge base.

    Raises on failure so the endpoint can return 503 — a silent fallback would
    risk the agent sending an ungrounded, possibly wrong answer to a client.
    """
    llm = build_assist_llm(temperature=0.2)

    from langchain_core.messages import HumanMessage, SystemMessage

    steer = f"\n\nConsigne de l'agent à respecter : {instruction}" if instruction else ""
    prompt = f"""Tu rédiges une proposition de réponse pour un AGENT HUMAIN du support I-Santé, qui la relira et l'ajustera avant de l'envoyer au client.

Règles :
- Base-toi UNIQUEMENT sur le contexte ci-dessous et la conversation. N'invente jamais de montant, de date, de taux ni de décision.
- Si l'information est insuffisante, dis-le honnêtement et propose la prochaine étape (pièce à fournir, vérification, délai).
- Les montants sont en dinars tunisiens (TND).
- Ton courtois et professionnel, en français, 2 à 5 phrases.

Contexte (base de connaissances I-Santé) :
{kb_context or "(aucun extrait pertinent trouvé)"}

Conversation :
{conversation_excerpt[:3000]}

Dernière demande du client à traiter : {query}{steer}

Proposition de réponse (prête à être relue par l'agent) :"""

    response = await asyncio.wait_for(
        llm.ainvoke([
            SystemMessage(content="Tu assistes les agents du support en rédigeant des propositions de réponse fiables, sourcées et prudentes."),
            HumanMessage(content=prompt),
        ]),
        timeout=20.0,
    )
    return response.content.strip()


# ==============================================================
# TOPICS + EXCERPTS
# ==============================================================

_TOPIC_KEYWORDS = {
    "remboursement": "Remboursement",
    "rembourse": "Remboursement",
    "dentaire": "Soins dentaires",
    "dent": "Soins dentaires",
    "optique": "Optique",
    "lunette": "Optique",
    "hospitalisation": "Hospitalisation",
    "hopital": "Hospitalisation",
    "urgence": "Urgences",
    "maternite": "Maternité",
    "naissance": "Maternité",
    "grossesse": "Maternité",
    "beneficiaire": "Bénéficiaires",
    "enfant": "Bénéficiaires",
    "conjoint": "Bénéficiaires",
    "carte": "Carte adhérent",
    "adherent": "Adhésion",
    "cotisation": "Cotisations",
    "prime": "Primes",
    "reclamation": "Réclamation",
    "plainte": "Réclamation",
    "medicament": "Pharmacie",
    "pharmacie": "Pharmacie",
    "consultation": "Consultation",
    "medecin": "Consultation",
    "kine": "Kinésithérapie",
    "labo": "Analyses",
    "analyse": "Analyses",
    "radio": "Imagerie",
    "irm": "Imagerie",
    "scanner": "Imagerie",
    "vaccin": "Vaccination",
    "dossier": "Dossiers",
    "prestation": "Prestations",
    "facture": "Facturation",
}


def extract_topics(text: str) -> list:
    """Extract key insurance-domain topics from user messages."""
    text_lower = text.lower()
    found = set()
    for keyword, topic in _TOPIC_KEYWORDS.items():
        if keyword in text_lower:
            found.add(topic)
    return list(found)[:6]  # Max 6 topics


def build_conversation_excerpt(history: list, max_messages: int = 10) -> str:
    """Build a text excerpt of the conversation for LLM summarization."""
    recent = history[-max_messages:] if len(history) > max_messages else history
    lines = []
    for msg in recent:
        role_label = {
            "user": "Client",
            "assistant": "IA",
            "agent": "Agent",
            "system": "Système",
        }.get(msg["role"], msg["role"])
        lines.append(f"{role_label}: {msg['content']}")
    return "\n".join(lines)


# ==============================================================
# CLIENT-CONTEXT NORMALIZERS
# The SOAP mappers (iway_soap_client) and the demo mocks (lookups) use
# different key names than the agent dossier UI. These map the typed contrat +
# untyped reimbursement rows onto the single shape the template binds to, so
# the panel is populated in BOTH mock and real mode.
# ==============================================================

def _pick(row: dict, *cands):
    """First non-empty value among candidate keys (case-insensitive)."""
    low = {str(k).lower(): v for k, v in row.items()}
    for c in cands:
        v = low.get(c)
        if v not in (None, ""):
            return v
    return None


def norm_real_contrat(contrat: Optional[dict], totaux: dict) -> Optional[dict]:
    if not isinstance(contrat, dict):
        return None
    return {
        "num_police": contrat.get("num_police"),
        "num_contrat": contrat.get("num_contrat"),
        "produit": contrat.get("type_remboursement"),
        "statut": contrat.get("situation"),
        "titulaire": contrat.get("titulaire"),
        "plafond_annuel": None,  # not exposed by the contrat DTO
        "consomme_annuel": (totaux or {}).get("total_rembourse"),
    }


def norm_real_dossier_row(row) -> dict:
    """Best-effort map an untyped SOAP reimbursement row onto the UI shape.
    Keys are validated against the live ERP; structural fields survive the
    _project_row whitelist (num*/statut/mnt*/date*) while names are stripped."""
    if not isinstance(row, dict):
        return {}
    return {
        "id": _pick(row, "numdossier", "num_dossier", "numero", "reference", "ref"),
        "type": _pick(row, "type", "nature", "libelle", "acte"),
        "montant": _pick(row, "montant", "mnttotal", "mnt", "total", "mntdossier"),
        "status": _pick(row, "statut", "status", "etat"),
        "date_soins": _pick(row, "datesoins", "datedossier", "date"),
        "montant_rembourse": _pick(row, "mntrembourse", "montantrembourse", "rembourse"),
    }
