"""
AI Insights Service — Gemini-powered topic clustering for failed queries.

Uses constrained Pydantic structured output to prevent LLM hallucinations.
Results are cached in-memory to avoid re-calling Gemini on every page load.
"""

import os
import json
import time
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("I-Way-Twin")

# ── Pydantic schemas for constrained LLM output ──

class TopicCluster(BaseModel):
    """A single identified knowledge gap topic."""
    topic: str = Field(description="Short professional topic name in French, 3-5 words max. Example: 'Remboursement Soins Dentaires'")
    query_count: int = Field(description="Number of queries in this cluster")
    sample_queries: List[str] = Field(description="2-3 representative sample queries from users", max_length=3)
    priority: str = Field(description="Priority level: 'critical', 'high', 'medium', or 'low'")
    suggestion: str = Field(description="One actionable sentence for the admin, in French")

class ClusteringResult(BaseModel):
    """The full clustering output from Gemini."""
    topics: List[TopicCluster] = Field(description="List of identified topic clusters, sorted by priority", max_length=8)
    summary: str = Field(description="One-sentence summary of the overall knowledge gap situation, in French")


# ── In-memory cache ──

_cache: dict = {
    "result": None,
    "timestamp": 0,
    "ttl_seconds": 300,  # 5 minutes
}


def _get_cached_result() -> Optional[ClusteringResult]:
    """Return cached result if still fresh."""
    if _cache["result"] and (time.time() - _cache["timestamp"]) < _cache["ttl_seconds"]:
        logger.info("📊 Insights cache HIT")
        return _cache["result"]
    return None


def _set_cache(result: ClusteringResult):
    """Store result in cache."""
    _cache["result"] = result
    _cache["timestamp"] = time.time()


async def cluster_failed_queries(failed_queries: List[dict]) -> ClusteringResult:
    """
    Use Gemini to cluster failed/low-confidence queries into business topics.
    
    Args:
        failed_queries: List of dicts with 'query', 'confidence', 'outcome' keys.
    
    Returns:
        ClusteringResult with clean, professional topic clusters.
    """
    # Check cache first
    cached = _get_cached_result()
    if cached:
        return cached

    # If no failed queries, return empty result
    if not failed_queries:
        return ClusteringResult(
            topics=[],
            summary="Aucune lacune détectée — toutes les requêtes ont été résolues avec succès."
        )

    # Prepare the query list for the prompt (limit to 50 to keep tokens low)
    query_list = []
    for q in failed_queries[:50]:
        conf_str = f"{q.get('confidence', 0):.0%}" if q.get('confidence') else "N/A"
        query_list.append(f"- \"{q['query']}\" (confidence: {conf_str}, outcome: {q.get('outcome', 'UNKNOWN')})")
    
    queries_text = "\n".join(query_list)

    system_prompt = """Tu es un analyste IA spécialisé dans l'assurance santé.
Ton rôle est d'analyser les requêtes utilisateur qui ont échoué ou obtenu une faible confiance,
et de les regrouper en thèmes métier cohérents.

RÈGLES STRICTES:
- Les noms de topics doivent être professionnels et spécifiques au domaine de l'assurance santé
- Ne jamais utiliser de mots génériques comme "Humain", "Système", "Origine"
- Chaque topic doit être un vrai sujet métier (ex: "Remboursement Optique", "Délai Hospitalisation")
- Les suggestions doivent être actionnables pour un administrateur
- Réponds UNIQUEMENT avec le JSON structuré demandé"""

    user_prompt = f"""Voici {len(failed_queries)} requêtes utilisateur qui ont échoué ou eu une faible confiance:

{queries_text}

Analyse ces requêtes et regroupe-les en 3 à 6 thèmes métier pertinents pour l'assurance santé.
Pour chaque thème, identifie les requêtes représentatives et propose une action concrète."""

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            temperature=0,
        )

        # Use structured output with Pydantic schema — this CONSTRAINS the LLM
        structured_llm = llm.with_structured_output(ClusteringResult)
        
        result = await structured_llm.ainvoke(f"{system_prompt}\n\n{user_prompt}")
        
        if isinstance(result, ClusteringResult):
            _set_cache(result)
            logger.info(f"📊 Gemini clustered {len(failed_queries)} queries into {len(result.topics)} topics")
            return result
        
        # Fallback if structured output returns something unexpected
        logger.warning("📊 Gemini returned unexpected type, falling back to rule-based")
        return _rule_based_clustering(failed_queries)

    except Exception as e:
        logger.error(f"📊 Gemini clustering failed: {e}, falling back to rule-based")
        return _rule_based_clustering(failed_queries)


def _rule_based_clustering(failed_queries: List[dict]) -> ClusteringResult:
    """
    Fallback: rule-based clustering using keyword matching.
    Used when Gemini is unavailable or fails.
    """
    # Insurance domain keyword groups
    DOMAIN_KEYWORDS = {
        "Remboursement & Prestations": ["remboursement", "rembourser", "prestation", "paiement", "montant", "tarif", "prix", "coût", "frais"],
        "Soins Dentaires": ["dentaire", "dent", "orthodontie", "prothèse", "couronne", "implant"],
        "Optique & Vision": ["optique", "lunettes", "lentilles", "vision", "ophtalmologie", "yeux"],
        "Hospitalisation": ["hôpital", "hospitalisation", "clinique", "chirurgie", "opération", "urgence"],
        "Gestion de Compte": ["mot de passe", "compte", "connexion", "profil", "matricule", "identifiant", "accès"],
        "Documents & Justificatifs": ["document", "justificatif", "attestation", "formulaire", "pièce", "dossier", "fichier", "télécharger"],
        "Couverture & Garanties": ["couverture", "garantie", "contrat", "police", "bénéficiaire", "assuré", "adhérent"],
        "Délais & Suivi": ["délai", "suivi", "statut", "attente", "traitement", "réponse", "quand"],
    }

    topic_matches: dict[str, list] = {}
    
    for q_data in failed_queries:
        query = q_data.get("query", "").lower()
        matched = False
        
        for topic_name, keywords in DOMAIN_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                if topic_name not in topic_matches:
                    topic_matches[topic_name] = []
                topic_matches[topic_name].append(q_data)
                matched = True
                break
        
        if not matched:
            other = "Requêtes Générales"
            if other not in topic_matches:
                topic_matches[other] = []
            topic_matches[other].append(q_data)

    # Build result
    topics = []
    for topic_name, queries in sorted(topic_matches.items(), key=lambda x: len(x[1]), reverse=True)[:6]:
        count = len(queries)
        priority = "critical" if count > 8 else "high" if count > 4 else "medium" if count > 2 else "low"
        samples = [q["query"] for q in queries[:3]]
        
        topics.append(TopicCluster(
            topic=topic_name,
            query_count=count,
            sample_queries=samples,
            priority=priority,
            suggestion=f"Créer ou enrichir la documentation sur '{topic_name}' — {count} requêtes ont échoué sur ce sujet.",
        ))

    total = len(failed_queries)
    return ClusteringResult(
        topics=topics,
        summary=f"{total} requêtes identifiées avec des lacunes, réparties en {len(topics)} thèmes principaux.",
    )
