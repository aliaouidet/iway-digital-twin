import os
import time
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Third-party imports
from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# --- 1. CONFIGURATION & LOGGING ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("I-Way-Twin")

SIMULATE_LATENCY = os.getenv("SIMULATE_LATENCY", "false").lower() == "true"

# --- 2. SECURITY & STATE (RSA Keys) ---
# Global state to hold keys and DB
class SystemState:
    private_key = None
    public_key_pem = None

state = SystemState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Generate RSA Keys
    logger.info(" Generating RSA 2048-bit Key Pair...")
    state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state.public_key_pem = state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    logger.info(" Digital Twin Online: Keys Generated & DB Loaded.")
    yield
    # Shutdown
    logger.info(" Digital Twin Shutting Down.")

app = FastAPI(
    title="I-Way Digital Twin",
    description="Simulator for Insurance Backend (Adherent/Prestataire)",
    version="1.0.0",
    lifespan=lifespan
)

# --- 3. IN-MEMORY DATABASE (PERSONAS) ---

MOCK_DB = {
    # Users
    "users": {
        "NADIA_2024": {
            "matricule": "NADIA_2024",
            "nom": "Mansour",
            "prenom": "Nadia",
            "role": "Adherent",
            "email": "nadia.mansour@email.com"
        },
        "DOC_AMINE": {
            "matricule": "DOC_AMINE",
            "nom": "Zaid",
            "prenom": "Amine",
            "role": "Prestataire",
            "specialite": "Cardiologie"
        }
    },
    # Knowledge Base (RAG Source)
    "knowledge_base": [
        {
            "id": 1,
            "question": "Comment ajouter un bénéficiaire ?",
            "reponse": "Rendez-vous dans l'espace 'Ma Famille', cliquez sur 'Ajouter' et téléchargez l'acte de naissance.",
            "cible": "Adherent",
            "tags": ["administratif", "famille"]
        },
        {
            "id": 2,
            "question": "Quel est le délai de remboursement ?",
            "reponse": "Les remboursements sont traités sous 48h ouvrées pour les feuilles de soins électroniques.",
            "cible": "Adherent",
            "tags": ["finance", "delai"]
        },
        {
            "id": 3,
            "question": "Comment facturer un acte hors nomenclature ?",
            "reponse": "Utilisez le code HN dans le formulaire de prestation et joignez le devis signé par le patient.",
            "cible": "Prestataire",
            "tags": ["facturation", "technique"]
        }
    ],
    # Beneficiaries (Linked to Adherents)
    "beneficiaires": {
        "NADIA_2024": [
            {"id": "B1", "nom": "Mansour", "prenom": "Sami", "lien": "Enfant", "date_naissance": "2015-06-12"},
            {"id": "B2", "nom": "Mansour", "prenom": "Karim", "lien": "Conjoint", "date_naissance": "1980-04-23"}
        ]
    },
    # Dossiers/Contracts
    "dossiers": {
        "NADIA_2024": [
            {"id": "DOS-8892", "type": "Santé Gold", "statut": "Actif", "date_effet": "2023-01-01"},
            {"id": "DOS-9901", "type": "Prévoyance", "statut": "En attente", "date_effet": "2024-03-01"}
        ]
    },
    # Prestations (Medical Acts)
    "prestations": {
        "NADIA_2024": [
            {"id": "PREST-101", "date": "2024-02-10", "acte": "Consultation Généraliste", "medecin": "Dr. House", "montant": 45.00}
        ],
        "DOC_AMINE": [
            {"id": "PREST-550", "date": "2024-02-14", "acte": "Echographie", "patient": "Mme. Ben Ali", "montant": 80.00}
        ]
    },
    # Remboursements (Finance)
    "remboursements": {
        "NADIA_2024": [
            {"id": "VIR-2024-01", "date": "2024-02-12", "montant": 31.50, "motif": "Remboursement Consult. Dr House", "status": "Payé"}
        ]
    },
    # Reclamations (Support Tickets)
    "reclamations": {
        "NADIA_2024": [
            {"id": "TICKET-001", "date": "2023-12-01", "objet": "Carte non reçue", "statut": "Clôturé"}
        ]
    }
}

# --- 4. PYDANTIC MODELS ---

class ReclamationInput(BaseModel):
    matricule: str
    objet: str
    message: str
    piece_jointe_base64: Optional[str] = None

class EscaladeInput(BaseModel):
    matricule: str
    conversation_id: str
    chat_history: List[Dict[str, Any]] = Field(..., description="Full JSON history of the chat")
    reason: Optional[str] = "User request"

# --- 5. DEPENDENCIES ---

async def get_current_user_matricule(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """
    Simulates Auth middleware.
    In real life, this decodes the JWT. Here, we trust the header for testing.
    Default to Nadia if no header provided.
    """
    if not x_user_id:
        return "NADIA_2024" 
    if x_user_id not in MOCK_DB["users"]:
        raise HTTPException(status_code=403, detail="User not found in Simulator DB")
    return x_user_id

# --- 6. API ENDPOINTS ---

@app.get("/", tags=["System"])
async def root():
    return {
        "system": "I-Way Digital Twin",
        "status": "operational",
        "personas_available": ["NADIA_2024 (Adherent)", "DOC_AMINE (Prestataire)"],
        "docs": "/docs"
    }

#  Auth & Profil
@app.get("/api/v1/me", tags=["Auth"])
async def get_me(matricule: str = Depends(get_current_user_matricule)):
    """Récupère les informations d'identité de l'utilisateur connecté."""
    user = MOCK_DB["users"][matricule]
    return user

#  Knowledge Base (RAG)
@app.get("/api/v1/knowledge-base", tags=["RAG Source"])
async def get_knowledge_base():
    """Extrait l'ensemble des règles métier pour l'indexation vectorielle."""
    return {
        "count": len(MOCK_DB["knowledge_base"]),
        "items": MOCK_DB["knowledge_base"]
    }

#  Données Métier (Adhérent/Prestataire)
@app.get("/api/v1/adherent/dossiers", tags=["Métier"])
async def get_dossiers(matricule: str):
    """Liste les dossiers médicaux ou administratifs."""
    return MOCK_DB["dossiers"].get(matricule, [])

@app.get("/api/v1/adherent/beneficiaires", tags=["Métier"])
async def get_beneficiaires(matricule: str):
    """Récupère la liste des personnes couvertes (conjoint, enfants)."""
    return MOCK_DB["beneficiaires"].get(matricule, [])

@app.get("/api/v1/prestations", tags=["Métier"])
async def get_prestations(matricule: str):
    """Détail technique des actes médicaux effectués."""
    return MOCK_DB["prestations"].get(matricule, [])

@app.get("/api/v1/remboursements", tags=["Métier"])
async def get_remboursements(matricule: str):
    """Historique financier des virements effectués."""
    return MOCK_DB["remboursements"].get(matricule, [])

#  Gestion des Réclamations
@app.get("/api/v1/reclamations", tags=["Support"])
async def get_reclamations_history(matricule: str):
    """Liste l'historique complet des tickets de support."""
    return MOCK_DB["reclamations"].get(matricule, [])

@app.post("/api/v1/reclamations", tags=["Support"])
async def create_reclamation(data: ReclamationInput):
    """Soumission d'un formulaire simple de réclamation."""
    if SIMULATE_LATENCY:
        time.sleep(1) # Simulate DB write delay
    
    new_ticket = {
        "id": f"TICKET-{uuid.uuid4().hex[:6].upper()}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objet": data.objet,
        "statut": "Ouvert",
        "message_preview": data.message[:50] + "..."
    }
    
    # Store in mock DB
    if data.matricule not in MOCK_DB["reclamations"]:
        MOCK_DB["reclamations"][data.matricule] = []
    MOCK_DB["reclamations"][data.matricule].append(new_ticket)
    
    logger.info(f"📩 New Reclamation from {data.matricule}: {data.objet}")
    return {"status": "success", "ticket": new_ticket}

@app.post("/api/v1/support/escalade", tags=["Support"])
async def escalate_to_human(data: EscaladeInput):
    """Endpoint critique pour l'envoi vers un agent humain."""
    logger.warning(f"ESCALATION TRIGGERED for {data.matricule}")
    logger.info(f"Context size: {len(data.chat_history)} messages")
    
    # In a real app, this would push to Salesforce/Zendesk
    return {
        "status": "escalated",
        "queue_position": 2,
        "estimated_wait": "5 minutes",
        "case_id": f"CASE-{uuid.uuid4().hex[:8]}"
    }

if __name__ == "__main__":
    import uvicorn
    print("\n I-Way Digital Twin is starting...")
    print(f" Default Persona (Adherent): NADIA_2024")
    print(f" Alternative Persona (Prestataire): DOC_AMINE")
    print(f" Docs available at: http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)