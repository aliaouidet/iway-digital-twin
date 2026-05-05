"""
Semantic Router — Fast embedding-based intent classification.

Replaces the LLM-based intent classification for simple queries.
Uses the existing sentence-transformers model to classify intents
via cosine similarity against pre-embedded example utterances.

Performance: ~50ms vs ~800ms for LLM-based classification.

Usage:
    from backend.domain.graph.semantic_router import classify_intent
    intent, confidence = classify_intent("Bonjour")
    # → ("small_talk", 0.92)
"""

import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger("I-Way-Twin")

# Lazy-loaded embeddings
_route_embeddings: Optional[dict] = None
_router_ready = False


# ── Example Utterances Per Intent ─────────────────────────────
# 20-30 examples per category for robust classification

INTENT_EXAMPLES = {
    "small_talk": [
        "Bonjour",
        "Salut",
        "Bonsoir",
        "Merci",
        "Merci beaucoup",
        "Au revoir",
        "Bonne journée",
        "Comment allez-vous ?",
        "Ça va ?",
        "OK",
        "D'accord",
        "Super",
        "Parfait",
        "Bien reçu",
        "Je vous remercie",
        "Salutations",
        "Hello",
        "Coucou",
        "Bonne soirée",
        "À bientôt",
    ],
    "info_query": [
        "Quel est le plafond dentaire ?",
        "Les IRM sont-elles couvertes ?",
        "Quel est le taux de remboursement pour les soins optiques ?",
        "Quels sont les délais de remboursement ?",
        "Comment fonctionne la prise en charge des urgences ?",
        "Quel est le numéro de support ?",
        "Quels sont les horaires de votre service client ?",
        "Quelles sont les garanties de mon contrat ?",
        "Comment ajouter un bénéficiaire ?",
        "Quel est le plafond annuel pour les médicaments ?",
        "Les prothèses dentaires sont-elles remboursées ?",
        "Quel est le délai de carence ?",
        "Comment fonctionne la prime de naissance ?",
        "Quels documents sont nécessaires pour un remboursement ?",
        "Quel est le montant de la prime de naissance ?",
        "Les lunettes sont-elles couvertes ?",
        "Comment contacter le service réclamation ?",
        "Quelle est la procédure pour une hospitalisation ?",
        "Les soins à l'étranger sont-ils couverts ?",
        "Quel est le taux de couverture pour les analyses ?",
        "Quelles sont les exclusions de ma police ?",
        "Comment résilier mon contrat ?",
        "Quels types de soins sont couverts ?",
        "Y a-t-il un plafond pour les consultations ?",
    ],
    "claim_action": [
        "Je veux soumettre un remboursement",
        "J'ai une facture de dentiste à rembourser",
        "Remboursement de 150 TND pour consultation",
        "Je veux déclarer un sinistre",
        "J'ai une facture de pharmacie à soumettre",
        "Remboursement pour une visite chez le médecin le 15 mars",
        "Je veux envoyer ma feuille de soins",
        "J'ai payé 200 TND chez l'opticien",
        "Demande de remboursement pour soins dentaires",
        "Je veux faire une réclamation pour mes lunettes",
        "Facture de 80 TND pour des analyses de sang",
        "J'ai une note d'honoraires à transmettre",
        "Remboursement pour une consultation chez Dr. Ahmed",
        "J'ai des frais de pharmacie de 45 TND",
        "Je veux déposer une demande de prise en charge",
        "Acte médical du 10 avril à rembourser",
        "Combien vais-je être remboursé pour cette facture ?",
        "J'ai une ordonnance à transmettre",
        "Je souhaite vérifier le statut de mon remboursement",
        "Ma demande de remboursement est en cours ?",
    ],
    "personal_lookup": [
        "Quels sont mes dossiers ?",
        "Montre-moi mes bénéficiaires",
        "Quel est l'état de mon dossier ?",
        "Liste mes remboursements en cours",
        "Qui sont mes ayants droit ?",
        "Montre-moi mon historique de remboursements",
        "Quels sont mes dossiers en attente ?",
        "Affiche mes informations personnelles",
        "Quel est mon solde de remboursement ?",
        "Combien de dossiers ai-je ouverts ?",
        "Montre mes dernières consultations",
        "Quels sont mes bénéficiaires actuels ?",
        "État de ma demande numéro 12345",
        "Voir mon profil adhérent",
        "Mes coordonnées sont-elles à jour ?",
        "Liste mes dossiers médicaux",
        "Quels sont mes droits en cours ?",
        "Afficher mes garanties actives",
        "Historique de mes sinistres",
        "Mes documents récents",
    ],
    "escalation": [
        "Je veux parler à un humain",
        "Transférez-moi à un agent",
        "C'est inacceptable",
        "Je suis mécontent",
        "Votre service est nul",
        "Je veux porter réclamation",
        "Passez-moi un responsable",
        "Je veux un superviseur",
        "C'est inadmissible",
        "Je suis en colère",
        "Ça fait trop longtemps que j'attends",
        "Je veux parler à quelqu'un",
        "Un agent humain s'il vous plaît",
        "Vos réponses ne m'aident pas",
        "Je veux escalader ma demande",
        "Connectez-moi à un conseiller",
        "Je ne suis pas satisfait",
        "C'est la troisième fois que je demande",
        "Je veux faire une plainte officielle",
        "Votre bot ne comprend rien",
    ],
}


def _initialize_router():
    """Pre-embed all example utterances using the existing sentence-transformers model."""
    global _route_embeddings, _router_ready

    if _router_ready:
        return

    try:
        from backend.services.rag_service import embed_texts

        _route_embeddings = {}
        for intent, examples in INTENT_EXAMPLES.items():
            embeddings = embed_texts(examples)
            _route_embeddings[intent] = np.array(embeddings)

        _router_ready = True
        total = sum(len(v) for v in INTENT_EXAMPLES.values())
        logger.info(f"🧭 Semantic router initialized ({total} examples across {len(INTENT_EXAMPLES)} intents)")

    except Exception as e:
        logger.warning(f"⚠️ Semantic router initialization failed: {e}")
        _router_ready = False


def classify_intent(text: str, threshold: float = 0.75) -> Tuple[Optional[str], float]:
    """
    Classify a user message into an intent category using embedding similarity.

    Args:
        text: The user's message
        threshold: Minimum similarity score to accept classification

    Returns:
        (intent_str, confidence) — intent is None if below threshold
    """
    if not _router_ready:
        _initialize_router()

    if not _router_ready or _route_embeddings is None:
        return None, 0.0

    try:
        from backend.services.rag_service import embed_text

        query_embedding = np.array(embed_text(text))

        best_intent = None
        best_score = 0.0

        for intent, embeddings_matrix in _route_embeddings.items():
            # Cosine similarity against all examples for this intent
            similarities = embeddings_matrix @ query_embedding
            # Use max similarity (best match against any example)
            max_sim = float(np.max(similarities))
            if max_sim > best_score:
                best_score = max_sim
                best_intent = intent

        if best_score >= threshold:
            logger.debug(f"🧭 Semantic router: '{text[:50]}' → {best_intent} ({best_score:.3f})")
            return best_intent, best_score
        else:
            logger.debug(f"🧭 Semantic router: '{text[:50]}' → below threshold ({best_score:.3f})")
            return None, best_score

    except Exception as e:
        logger.warning(f"Semantic router classification failed: {e}")
        return None, 0.0
