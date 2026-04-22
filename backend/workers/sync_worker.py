"""
Sync Worker — Pulls knowledge from I-Way mock API, chunks, embeds, and upserts.

This runs:
  - As a Celery periodic task (every 5 minutes via beat schedule)
  - On-demand via REST API trigger (POST /api/v1/knowledge/sync)
  - At startup (initial sync via main.py lifespan)

Phase 6: Enhanced with RecursiveCharacterTextSplitter chunking and
PGVector persistence (falls back to in-memory if DB is unavailable).
"""

import logging

from backend.workers.celery_app import celery_app
from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


# ==============================================================
# MOCK POLICY DOCUMENTS — Rich I-Way insurance policy corpus
# ==============================================================
# These supplement the MOCK_KB Q&A pairs with longer-form policy
# documents that benefit from chunking.

IWAY_POLICY_DOCUMENTS = [
    {
        "id": "POL-001",
        "title": "Barème des Remboursements I-Way 2024",
        "content": (
            "Barème général des remboursements I-Way applicable à partir du 1er janvier 2024.\n\n"
            "Consultations médicales: Les consultations chez un médecin généraliste conventionné sont remboursées "
            "à 100% du tarif conventionné (45 TND). Les consultations chez un spécialiste conventionné sont remboursées "
            "à 80% du tarif conventionné. Les consultations hors convention sont remboursées sur la base du tarif "
            "conventionné avec un reste à charge plus élevé.\n\n"
            "Soins dentaires: Le plafond annuel pour les soins dentaires est de 600 TND par bénéficiaire. "
            "Les prothèses dentaires sont couvertes à 70% dans la limite de ce plafond. Les implants dentaires "
            "sont couverts à 50% avec un plafond de 1000 TND par implant. Les soins orthodontiques pour les "
            "enfants de moins de 16 ans bénéficient d'un plafond supplémentaire de 400 TND.\n\n"
            "Soins optiques: Le plafond annuel pour les verres et montures est de 250 TND. Les lentilles de contact "
            "sont couvertes à hauteur de 150 TND par an sur prescription médicale. Le renouvellement est autorisé "
            "tous les 2 ans sauf changement de correction supérieur à 0.5 dioptrie.\n\n"
            "Pharmacie: Les médicaments génériques sont remboursés à 80%. Les médicaments de marque sont remboursés "
            "à 60%. Les médicaments de confort et les compléments alimentaires ne sont pas couverts. "
            "Le réseau de tiers payant comprend 450 pharmacies conventionnées en Tunisie.\n\n"
            "Hospitalisation: Couverture à 90% dans les établissements conventionnés, 70% hors convention. "
            "Chambre individuelle: supplément de 50 TND/jour. Les frais d'accompagnant pour enfants de moins "
            "de 12 ans sont couverts à 100%."
        ),
        "cible": "Adherent",
        "tags": ["barème", "remboursement", "tarif", "couverture"],
    },
    {
        "id": "POL-002",
        "title": "Procédures d'Accord Préalable",
        "content": (
            "Guide des procédures d'accord préalable I-Way.\n\n"
            "Actes nécessitant un accord préalable obligatoire:\n"
            "- Hospitalisation programmée (délai de réponse: 48h)\n"
            "- Prothèses dentaires supérieures à 200 TND\n"
            "- IRM et examens de médecine nucléaire\n"
            "- Chirurgie ambulatoire hors nomenclature standard\n"
            "- Kinésithérapie au-delà de 30 séances annuelles\n"
            "- Fécondation in vitro (FIV)\n\n"
            "Procédure de demande:\n"
            "1. Connectez-vous à votre espace adhérent\n"
            "2. Rendez-vous dans 'Mes Prestations' > 'Demande d'accord préalable'\n"
            "3. Téléchargez le devis détaillé du praticien\n"
            "4. Le médecin conseil I-Way étudie votre dossier\n"
            "5. Réponse sous 48h ouvrées\n\n"
            "En cas de non-réponse sous 5 jours ouvrés, l'accord est considéré comme tacitement accepté. "
            "En cas de refus, vous disposez de 30 jours pour formuler un recours auprès de la commission médicale.\n\n"
            "Urgences: Aucun accord préalable n'est requis pour les hospitalisations d'urgence. "
            "Contactez le service client dans les 48h suivant l'admission pour la prise en charge."
        ),
        "cible": "Adherent",
        "tags": ["accord", "préalable", "procédure", "hospitalisation"],
    },
    {
        "id": "POL-003",
        "title": "Convention Prestataire I-Way — Conditions et Tarifs",
        "content": (
            "Conditions de conventionnement pour les prestataires de soins I-Way.\n\n"
            "Éligibilité: Tout professionnel de santé inscrit à l'ordre professionnel correspondant "
            "peut demander le conventionnement I-Way. Les spécialités suivantes sont prioritaires: "
            "médecine générale, dentaire, ophtalmologie, cardiologie, radiologie, kinésithérapie.\n\n"
            "Avantages du conventionnement:\n"
            "- Paiement garanti sous 72h ouvrées pour les factures électroniques\n"
            "- Accès au système de tiers payant I-Way\n"
            "- Visibilité dans l'annuaire des prestataires I-Way\n"
            "- Formation gratuite à l'utilisation du portail prestataire\n\n"
            "Facturation: Les actes sont facturés selon la nomenclature I-Way. Les actes hors nomenclature "
            "utilisent le code HN et nécessitent un devis signé par le patient. L'accord préalable est requis "
            "pour tout montant supérieur à 200 TND.\n\n"
            "Délais de paiement: Factures électroniques: 72h ouvrées. Factures papier: 15 jours ouvrés. "
            "En cas de contestation, le prestataire dispose de 60 jours pour formuler une réclamation."
        ),
        "cible": "Prestataire",
        "tags": ["convention", "prestataire", "facturation", "paiement"],
    },
    {
        "id": "POL-004",
        "title": "Maladies Chroniques — Protocole ALD I-Way",
        "content": (
            "Protocole de prise en charge des Affections de Longue Durée (ALD) par I-Way.\n\n"
            "Les 30 maladies chroniques reconnues par I-Way incluent: diabète (type 1 et 2), "
            "hypertension artérielle, asthme sévère, insuffisance cardiaque, insuffisance rénale chronique, "
            "cancers, maladies auto-immunes, hépatites chroniques B et C, VIH/SIDA, épilepsie, "
            "maladie de Parkinson, sclérose en plaques, polyarthrite rhumatoïde, lupus, "
            "maladie de Crohn, rectocolite hémorragique, mucoviscidose, drépanocytose, thalassémie.\n\n"
            "Prise en charge: 100% des frais liés à la pathologie après validation du dossier ALD "
            "par le médecin conseil. Le protocole de soins est renouvelé annuellement.\n\n"
            "Procédure de déclaration:\n"
            "1. Certificat médical détaillé du médecin traitant\n"
            "2. Résultats d'examens datant de moins de 3 mois\n"
            "3. Formulaire 'Déclaration ALD' complété\n"
            "4. Étude du dossier par le médecin conseil sous 10 jours ouvrés\n\n"
            "Suivi: Les analyses trimestrielles de suivi sont couvertes intégralement. "
            "Les médicaments du protocole ALD sont remboursés à 100%."
        ),
        "cible": "Adherent",
        "tags": ["chronique", "ALD", "maladie", "protocole"],
    },
]


@celery_app.task(
    name="backend.workers.sync_worker.sync_knowledge_base",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_knowledge_base(self):
    """
    Celery task: Full knowledge sync pipeline.
    
    1. Fetch Q&A entries (from real I-Way API or MOCK_KB)
    2. Merge with policy documents (IWAY_POLICY_DOCUMENTS)
    3. Chunk using RecursiveCharacterTextSplitter
    4. Embed using sentence-transformers
    5. Upsert into PGVector (or in-memory fallback)
    
    Toggle: Set IWAY_USE_REAL_API=true to fetch from the real API.
    """
    try:
        from backend.services.rag_service import sync_knowledge_from_api

        if settings.IWAY_USE_REAL_API:
            # Real API — fetch via HTTP (sync since we're in a Celery worker)
            import httpx
            resp = httpx.get(
                f"{settings.IWAY_API_BASE_URL}/api/v1/knowledge-base",
                headers={"X-API-Key": settings.IWAY_API_KEY} if settings.IWAY_API_KEY else {},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            logger.info(f"[SyncWorker] Fetched {len(items)} items from real API")
        else:
            # Mock data — direct import (no network dependency)
            from backend.routers.iway_mock import MOCK_KB
            items = MOCK_KB

        # Merge with policy documents (convert to Q&A format for unified pipeline)
        policy_items = _policy_docs_to_kb_format(IWAY_POLICY_DOCUMENTS)
        all_items = items + policy_items

        if not all_items:
            logger.warning("[SyncWorker] No knowledge items available")
            return {"status": "empty", "synced": 0}

        # Sync (chunk + embed + upsert)
        result = sync_knowledge_from_api(all_items)
        logger.info(f"[SyncWorker] Sync complete: {result}")
        return result

    except Exception as exc:
        logger.error(f"[SyncWorker] Unexpected error: {exc}")
        self.retry(exc=exc)


def sync_knowledge_direct():
    """
    Direct sync (non-Celery) — for startup and on-demand API calls.
    Called from main.py lifespan or from the REST API.
    
    Merges MOCK_KB (33 Q&A entries) with IWAY_POLICY_DOCUMENTS (4 policy docs).
    """
    from backend.services.rag_service import sync_knowledge_from_api
    from backend.routers.iway_mock import MOCK_KB

    # Merge with policy documents
    policy_items = _policy_docs_to_kb_format(IWAY_POLICY_DOCUMENTS)
    all_items = MOCK_KB + policy_items

    logger.info(f"[SyncDirect] Syncing {len(MOCK_KB)} Q&A + {len(policy_items)} policy docs = {len(all_items)} total")
    result = sync_knowledge_from_api(all_items)
    return result


def _policy_docs_to_kb_format(policy_docs: list) -> list:
    """Convert policy documents to the same format as MOCK_KB entries.
    
    This allows the unified sync_knowledge_from_api pipeline to handle
    both Q&A entries and longer policy documents with the same code path.
    """
    kb_format = []
    for doc in policy_docs:
        kb_format.append({
            "id": doc["id"],
            "question": doc["title"],
            "reponse": doc["content"],
            "cible": doc.get("cible", ""),
            "tags": doc.get("tags", []),
        })
    return kb_format
