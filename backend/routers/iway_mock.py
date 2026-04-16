"""
Mock I-Way API Router — Simulates I-Way's insurance backend.

These endpoints represent I-Way's real systems that your Digital Twin
consumes via API calls. In production, these would be replaced by
actual I-Way service endpoints.

Routes:
  GET  /api/v1/knowledge-base
  GET  /api/v1/me
  GET  /api/v1/adherent/dossiers
  GET  /api/v1/adherent/beneficiaires
  GET  /api/v1/prestations
  GET  /api/v1/remboursements
  GET  /api/v1/reclamations
  POST /api/v1/reclamations
  POST /api/v1/support/escalade
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.routers.auth import get_current_user, MOCK_USERS

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1", tags=["I-Way Mock API"])

# --- Mock domain data (simulates I-Way's database) ---

MOCK_KB = [
    {"id": 1, "question": "Comment ajouter un beneficiaire ?", "reponse": "Rendez-vous dans l'espace 'Ma Famille', cliquez sur 'Ajouter' et telechargez l'acte de naissance ou le livret de famille. Le beneficiaire sera actif sous 24h apres validation.", "cible": "Adherent", "tags": ["administratif", "famille"]},
    {"id": 2, "question": "Quel est le delai de remboursement ?", "reponse": "Les remboursements sont traites sous 48h ouvrees pour les feuilles de soins electroniques (FSE). Les feuilles papier peuvent prendre jusqu'a 15 jours ouvres. Les virements sont effectues sur le RIB enregistre dans votre espace.", "cible": "Adherent", "tags": ["finance", "delai"]},
    {"id": 3, "question": "Comment facturer un acte hors nomenclature ?", "reponse": "Utilisez le code HN dans le formulaire de prestation et joignez le devis signe par le patient. L'accord prealable de la mutuelle est requis pour tout montant superieur a 200 TND.", "cible": "Prestataire", "tags": ["facturation", "technique"]},
    {"id": 4, "question": "Quel est le plafond annuel pour les soins dentaires ?", "reponse": "Selon l'Article 4 de la convention, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire. Les protheses dentaires sont couvertes a 70% dans la limite de ce plafond. Les soins orthodontiques pour les enfants de moins de 16 ans beneficient d'un plafond supplementaire de 400 TND.", "cible": "Adherent", "tags": ["dentaire", "plafond", "couverture"]},
    {"id": 5, "question": "Quelle est la prime de naissance ?", "reponse": "La prime de naissance est de 300 TND par enfant, versee sur presentation de l'acte de naissance dans un delai de 30 jours suivant la naissance. En cas de naissances multiples, la prime est versee pour chaque enfant. La demande se fait via l'espace 'Mes Prestations'.", "cible": "Adherent", "tags": ["naissance", "prime", "famille"]},
    {"id": 6, "question": "Comment fonctionne la prise en charge hospitaliere ?", "reponse": "L'hospitalisation est couverte a 90% dans les etablissements conventionnes et 70% hors convention. Une entente prealable est obligatoire pour les hospitalisations programmees (delai de reponse: 48h). Les urgences sont prises en charge directement sur presentation de la carte d'adherent.", "cible": "Adherent", "tags": ["hospitalisation", "couverture", "urgence"]},
    {"id": 7, "question": "Quels sont les plafonds pour les soins optiques ?", "reponse": "Les soins optiques sont couverts avec un plafond de 250 TND par an pour les verres et montures. Les lentilles de contact sont couvertes a hauteur de 150 TND par an sur prescription medicale. Le renouvellement est autorise tous les 2 ans sauf changement de correction.", "cible": "Adherent", "tags": ["optique", "lunettes", "plafond"]},
    {"id": 8, "question": "Comment se faire rembourser les medicaments ?", "reponse": "Les medicaments prescrits sont rembourses a 80% pour les medicaments generiques et 60% pour les medicaments de marque. Les medicaments de confort ne sont pas couverts. Presentez votre ordonnance et la facture de la pharmacie via l'espace 'Remboursements'.", "cible": "Adherent", "tags": ["pharmacie", "medicaments", "remboursement"]},
    {"id": 9, "question": "Quelles sont les conditions pour les maladies chroniques ?", "reponse": "Les maladies chroniques (diabete, hypertension, asthme, etc.) beneficient d'une prise en charge a 100% apres validation du dossier par le medecin conseil. Le protocole de soins doit etre renouvele chaque annee. Les analyses de suivi trimestrielles sont couvertes integralement.", "cible": "Adherent", "tags": ["chronique", "maladie", "couverture"]},
    {"id": 10, "question": "Comment fonctionne le conge maternite ?", "reponse": "Le conge maternite est de 30 jours avant la date prevue et 40 jours apres l'accouchement. Les frais d'accouchement sont couverts a 100% dans les cliniques conventionnees. Les visites prenatales et les echographies de suivi sont prises en charge integralement.", "cible": "Adherent", "tags": ["maternite", "conge", "accouchement"]},
    {"id": 11, "question": "Que faire en cas d'urgence medicale ?", "reponse": "En cas d'urgence, rendez-vous aux services d'urgence les plus proches. Les frais seront pris en charge a 100% sur presentation de votre carte d'adherent. Si vous etes hospitalise en urgence, contactez le service client dans les 48h pour la prise en charge. Le numero d'urgence I-Way est le 71 800 800.", "cible": "Adherent", "tags": ["urgence", "hospitalisation", "contact"]},
    {"id": 12, "question": "Comment devenir prestataire conventionne I-Way ?", "reponse": "Pour devenir prestataire conventionne, soumettez votre dossier via le portail prestataire avec: copie du diplome, inscription a l'ordre, RIB professionnel, et attestation d'assurance RC. La commission de conventionnement se reunit mensuellement. Le taux de conventionnement varie selon la specialite.", "cible": "Prestataire", "tags": ["convention", "prestataire", "inscription"]},
]

MOCK_BENEFICIAIRES = {
    "12345": [
        {"id": "B1", "nom": "Mansour", "prenom": "Sami", "lien": "Enfant", "date_naissance": "2015-06-12"},
        {"id": "B2", "nom": "Mansour", "prenom": "Karim", "lien": "Conjoint", "date_naissance": "1980-04-23"}
    ]
}

MOCK_DOSSIERS = {
    "12345": [
        {"id": "DOS-8892", "type": "Santé Gold", "statut": "Actif", "date_effet": "2023-01-01"},
        {"id": "DOS-9901", "type": "Prévoyance", "statut": "En attente", "date_effet": "2024-03-01"}
    ]
}

MOCK_PRESTATIONS = {
    "12345": [{"id": "PREST-101", "date": "2024-02-10", "acte": "Consultation Généraliste", "medecin": "Dr. House", "montant": 45.00}],
    "99999": [{"id": "PREST-550", "date": "2024-02-14", "acte": "Echographie", "patient": "Mme. Ben Ali", "montant": 80.00}],
}

MOCK_REMBOURSEMENTS = {
    "12345": [{"id": "VIR-2024-01", "date": "2024-02-12", "montant": 31.50, "motif": "Remboursement Consult. Dr House", "status": "Payé"}]
}

MOCK_RECLAMATIONS = {
    "12345": [{"id": "TICKET-001", "date": "2023-12-01", "objet": "Carte non reçue", "statut": "Clôturé"}]
}

MOCK_ESCALATION_TICKETS = []


# --- Pydantic Models ---

class ReclamationInput(BaseModel):
    matricule: str
    objet: str
    message: str
    piece_jointe_base64: Optional[str] = None

class EscaladeInput(BaseModel):
    matricule: str
    conversation_id: str = Field(default_factory=lambda: f"conv-{uuid.uuid4().hex[:8]}")
    chat_history: List[Dict[str, Any]] = Field(..., description="Full JSON history of the chat")
    reason: Optional[str] = "User request"


# --- Endpoints ---

@router.get("/knowledge-base", tags=["RAG Source"])
async def get_knowledge_base():
    """Extrait l'ensemble des règles métier pour l'indexation vectorielle."""
    return {"count": len(MOCK_KB), "items": MOCK_KB}


@router.get("/me", tags=["Profile"])
async def get_me(matricule: str = Depends(get_current_user)):
    """Récupère les informations d'identité de l'utilisateur connecté."""
    user = MOCK_USERS[matricule]
    return {k: v for k, v in user.items() if k != "password"}


@router.get("/adherent/dossiers", tags=["Métier"])
async def get_dossiers(matricule: str = Depends(get_current_user)):
    return MOCK_DOSSIERS.get(matricule, [])


@router.get("/adherent/beneficiaires", tags=["Métier"])
async def get_beneficiaires(matricule: str = Depends(get_current_user)):
    return MOCK_BENEFICIAIRES.get(matricule, [])


@router.get("/prestations", tags=["Métier"])
async def get_prestations(matricule: str = Depends(get_current_user)):
    return MOCK_PRESTATIONS.get(matricule, [])


@router.get("/remboursements", tags=["Métier"])
async def get_remboursements(matricule: str = Depends(get_current_user)):
    return MOCK_REMBOURSEMENTS.get(matricule, [])


@router.get("/reclamations", tags=["Support"])
async def get_reclamations_history(matricule: str = Depends(get_current_user)):
    return MOCK_RECLAMATIONS.get(matricule, [])


@router.post("/reclamations", tags=["Support"])
async def create_reclamation(data: ReclamationInput, matricule: str = Depends(get_current_user)):
    new_ticket = {
        "id": f"TICKET-{uuid.uuid4().hex[:6].upper()}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objet": data.objet,
        "statut": "Ouvert",
        "message_preview": data.message[:50] + "..."
    }
    if data.matricule not in MOCK_RECLAMATIONS:
        MOCK_RECLAMATIONS[data.matricule] = []
    MOCK_RECLAMATIONS[data.matricule].append(new_ticket)
    logger.info(f"📩 New Reclamation from {data.matricule}: {data.objet}")
    return {"status": "success", "ticket": new_ticket}


@router.post("/support/escalade", tags=["Support"])
async def escalate_to_human(data: EscaladeInput, matricule: str = Depends(get_current_user)):
    logger.warning(f"🚨 ESCALATION TRIGGERED for {data.matricule}")
    user = MOCK_USERS.get(data.matricule, {})
    ticket = {
        "case_id": f"CASE-{uuid.uuid4().hex[:8]}",
        "status": "escalated",
        "queue_position": 2,
        "estimated_wait": "5 minutes",
        "matricule": data.matricule,
        "client_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
        "client_role": user.get("role", "Unknown"),
        "reason": data.reason,
        "chat_history": data.chat_history,
        "created_at": datetime.now().isoformat()
    }
    MOCK_ESCALATION_TICKETS.append(ticket)
    return {
        "status": "escalated",
        "queue_position": ticket["queue_position"],
        "estimated_wait": ticket["estimated_wait"],
        "case_id": ticket["case_id"]
    }


@router.get("/dashboard/tickets", tags=["Dashboard"])
async def get_escalation_tickets(matricule: str = Depends(get_current_user)):
    return MOCK_ESCALATION_TICKETS
