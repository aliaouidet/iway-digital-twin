import os
import time
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

# Third-party imports
from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt  # PyJWT

# --- 1. CONFIGURATION & LOGGING ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("I-Way-Twin")

SIMULATE_LATENCY = os.getenv("SIMULATE_LATENCY", "false").lower() == "true"
JWT_ALGORITHM = "RS256"
JWT_EXPIRATION_MINUTES = 60

# --- 2. SECURITY & STATE (RSA Keys) ---
class SystemState:
    private_key = None
    public_key_pem = None

state = SystemState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Generate RSA Keys
    logger.info("🔐 Generating RSA 2048-bit Key Pair...")
    state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state.public_key_pem = state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    logger.info("✅ Digital Twin Online: Keys Generated & DB Loaded.")
    yield
    # Shutdown
    logger.info("🛑 Digital Twin Shutting Down.")

app = FastAPI(
    title="I-Way Digital Twin",
    description="Simulator for Insurance Backend (Adherent/Prestataire)",
    version="1.0.0",
    lifespan=lifespan
)

# --- 3. IN-MEMORY DATABASE (PERSONAS) ---

MOCK_DB = {
    # Users — matricules and passwords per spec
    "users": {
        "12345": {
            "matricule": "12345",
            "nom": "Mansour",
            "prenom": "Nadia",
            "role": "Adherent",
            "email": "nadia.mansour@email.com",
            "password": "pass"
        },
        "99999": {
            "matricule": "99999",
            "nom": "Zaid",
            "prenom": "Amine",
            "role": "Prestataire",
            "specialite": "Cardiologie",
            "password": "med"
        }
    },
    # Knowledge Base (RAG Source)
    "knowledge_base": [
        {
            "id": 1,
            "question": "Comment ajouter un beneficiaire ?",
            "reponse": "Rendez-vous dans l'espace 'Ma Famille', cliquez sur 'Ajouter' et telechargez l'acte de naissance ou le livret de famille. Le beneficiaire sera actif sous 24h apres validation.",
            "cible": "Adherent",
            "tags": ["administratif", "famille"]
        },
        {
            "id": 2,
            "question": "Quel est le delai de remboursement ?",
            "reponse": "Les remboursements sont traites sous 48h ouvrees pour les feuilles de soins electroniques (FSE). Les feuilles papier peuvent prendre jusqu'a 15 jours ouvres. Les virements sont effectues sur le RIB enregistre dans votre espace.",
            "cible": "Adherent",
            "tags": ["finance", "delai"]
        },
        {
            "id": 3,
            "question": "Comment facturer un acte hors nomenclature ?",
            "reponse": "Utilisez le code HN dans le formulaire de prestation et joignez le devis signe par le patient. L'accord prealable de la mutuelle est requis pour tout montant superieur a 200 TND.",
            "cible": "Prestataire",
            "tags": ["facturation", "technique"]
        },
        {
            "id": 4,
            "question": "Quel est le plafond annuel pour les soins dentaires ?",
            "reponse": "Selon l'Article 4 de la convention, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire. Les protheses dentaires sont couvertes a 70% dans la limite de ce plafond. Les soins orthodontiques pour les enfants de moins de 16 ans beneficient d'un plafond supplementaire de 400 TND.",
            "cible": "Adherent",
            "tags": ["dentaire", "plafond", "couverture"]
        },
        {
            "id": 5,
            "question": "Quelle est la prime de naissance ?",
            "reponse": "La prime de naissance est de 300 TND par enfant, versee sur presentation de l'acte de naissance dans un delai de 30 jours suivant la naissance. En cas de naissances multiples, la prime est versee pour chaque enfant. La demande se fait via l'espace 'Mes Prestations'.",
            "cible": "Adherent",
            "tags": ["naissance", "prime", "famille"]
        },
        {
            "id": 6,
            "question": "Comment fonctionne la prise en charge hospitaliere ?",
            "reponse": "L'hospitalisation est couverte a 90% dans les etablissements conventionnes et 70% hors convention. Une entente prealable est obligatoire pour les hospitalisations programmees (delai de reponse: 48h). Les urgences sont prises en charge directement sur presentation de la carte d'adherent.",
            "cible": "Adherent",
            "tags": ["hospitalisation", "couverture", "urgence"]
        },
        {
            "id": 7,
            "question": "Quels sont les plafonds pour les soins optiques ?",
            "reponse": "Les soins optiques sont couverts avec un plafond de 250 TND par an pour les verres et montures. Les lentilles de contact sont couvertes a hauteur de 150 TND par an sur prescription medicale. Le renouvellement est autorise tous les 2 ans sauf changement de correction.",
            "cible": "Adherent",
            "tags": ["optique", "lunettes", "plafond"]
        },
        {
            "id": 8,
            "question": "Comment se faire rembourser les medicaments ?",
            "reponse": "Les medicaments prescrits sont rembourses a 80% pour les medicaments generiques et 60% pour les medicaments de marque. Les medicaments de confort ne sont pas couverts. Presentez votre ordonnance et la facture de la pharmacie via l'espace 'Remboursements'.",
            "cible": "Adherent",
            "tags": ["pharmacie", "medicaments", "remboursement"]
        },
        {
            "id": 9,
            "question": "Quelles sont les conditions pour les maladies chroniques ?",
            "reponse": "Les maladies chroniques (diabete, hypertension, asthme, etc.) beneficient d'une prise en charge a 100% apres validation du dossier par le medecin conseil. Le protocole de soins doit etre renouvele chaque annee. Les analyses de suivi trimestrielles sont couvertes integralement.",
            "cible": "Adherent",
            "tags": ["chronique", "maladie", "couverture"]
        },
        {
            "id": 10,
            "question": "Comment fonctionne le conge maternite ?",
            "reponse": "Le conge maternite est de 30 jours avant la date prevue et 40 jours apres l'accouchement. Les frais d'accouchement sont couverts a 100% dans les cliniques conventionnees. Les visites prenatales et les echographies de suivi sont prises en charge integralement.",
            "cible": "Adherent",
            "tags": ["maternite", "conge", "accouchement"]
        },
        {
            "id": 11,
            "question": "Que faire en cas d'urgence medicale ?",
            "reponse": "En cas d'urgence, rendez-vous aux services d'urgence les plus proches. Les frais seront pris en charge a 100% sur presentation de votre carte d'adherent. Si vous etes hospitalise en urgence, contactez le service client dans les 48h pour la prise en charge. Le numero d'urgence I-Way est le 71 800 800.",
            "cible": "Adherent",
            "tags": ["urgence", "hospitalisation", "contact"]
        },
        {
            "id": 12,
            "question": "Comment devenir prestataire conventionne I-Way ?",
            "reponse": "Pour devenir prestataire conventionne, soumettez votre dossier via le portail prestataire avec: copie du diplome, inscription a l'ordre, RIB professionnel, et attestation d'assurance RC. La commission de conventionnement se reunit mensuellement. Le taux de conventionnement varie selon la specialite.",
            "cible": "Prestataire",
            "tags": ["convention", "prestataire", "inscription"]
        },
    ],
    # Beneficiaries (Linked to Adherents)
    "beneficiaires": {
        "12345": [
            {"id": "B1", "nom": "Mansour", "prenom": "Sami", "lien": "Enfant", "date_naissance": "2015-06-12"},
            {"id": "B2", "nom": "Mansour", "prenom": "Karim", "lien": "Conjoint", "date_naissance": "1980-04-23"}
        ]
    },
    # Dossiers/Contracts
    "dossiers": {
        "12345": [
            {"id": "DOS-8892", "type": "Santé Gold", "statut": "Actif", "date_effet": "2023-01-01"},
            {"id": "DOS-9901", "type": "Prévoyance", "statut": "En attente", "date_effet": "2024-03-01"}
        ]
    },
    # Prestations (Medical Acts)
    "prestations": {
        "12345": [
            {"id": "PREST-101", "date": "2024-02-10", "acte": "Consultation Généraliste", "medecin": "Dr. House", "montant": 45.00}
        ],
        "99999": [
            {"id": "PREST-550", "date": "2024-02-14", "acte": "Echographie", "patient": "Mme. Ben Ali", "montant": 80.00}
        ]
    },
    # Remboursements (Finance)
    "remboursements": {
        "12345": [
            {"id": "VIR-2024-01", "date": "2024-02-12", "montant": 31.50, "motif": "Remboursement Consult. Dr House", "status": "Payé"}
        ]
    },
    # Reclamations (Support Tickets)
    "reclamations": {
        "12345": [
            {"id": "TICKET-001", "date": "2023-12-01", "objet": "Carte non reçue", "statut": "Clôturé"}
        ]
    },
    # Escalation tickets (for the dashboard)
    "escalation_tickets": []
}

# --- 4. PYDANTIC MODELS ---

class LoginInput(BaseModel):
    matricule: str
    password: str

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

# --- 5. SECURITY DEPENDENCIES ---

bearer_scheme = HTTPBearer()

def create_jwt(matricule: str) -> str:
    """Create an RS256-signed JWT for the given matricule."""
    payload = {
        "sub": matricule,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES),
        "iss": "i-way-digital-twin"
    }
    private_key_pem = state.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return jwt.encode(payload, private_key_pem, algorithm=JWT_ALGORITHM)

def verify_jwt(token: str) -> dict:
    """Verify and decode an RS256 JWT. Returns the payload or raises."""
    try:
        payload = jwt.decode(
            token,
            state.public_key_pem,
            algorithms=[JWT_ALGORITHM],
            issuer="i-way-digital-twin"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """
    FastAPI dependency: extracts the Bearer token, verifies it,
    and returns the matricule from the JWT subject claim.
    """
    payload = verify_jwt(credentials.credentials)
    matricule = payload.get("sub")
    if matricule not in MOCK_DB["users"]:
        raise HTTPException(status_code=403, detail="User not found in Simulator DB")
    return matricule

# --- 6. AUTH ENDPOINTS (Public) ---

@app.post("/auth/login", tags=["Auth"])
async def login(data: LoginInput):
    """Authenticate with matricule + password, receive an RS256-signed JWT."""
    user = MOCK_DB["users"].get(data.matricule)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid matricule or password")

    token = create_jwt(data.matricule)
    logger.info(f"🔑 Login successful for {data.matricule} ({user['prenom']} {user['nom']})")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRATION_MINUTES * 60,
        "user": {
            "matricule": user["matricule"],
            "nom": user["nom"],
            "prenom": user["prenom"],
            "role": user["role"]
        }
    }

@app.get("/auth/public-key", tags=["Auth"])
async def get_public_key():
    """Expose the RSA public key (PEM) for external JWT verification."""
    return {
        "algorithm": JWT_ALGORITHM,
        "public_key": state.public_key_pem.decode("utf-8")
    }

# --- 7. SYSTEM ENDPOINTS (Public) ---

@app.get("/", tags=["System"])
async def root():
    return {
        "system": "I-Way Digital Twin",
        "status": "operational",
        "personas_available": [
            "12345 / pass (Nadia – Adherent)",
            "99999 / med  (Dr. Amine – Prestataire)"
        ],
        "auth": "POST /auth/login with {matricule, password}",
        "docs": "/docs"
    }

@app.get("/api/v1/knowledge-base", tags=["RAG Source"])
async def get_knowledge_base():
    """Extrait l'ensemble des règles métier pour l'indexation vectorielle."""
    return {
        "count": len(MOCK_DB["knowledge_base"]),
        "items": MOCK_DB["knowledge_base"]
    }

# --- 8. PROTECTED ENDPOINTS (Require Bearer JWT) ---

# Profile
@app.get("/api/v1/me", tags=["Profile"])
async def get_me(matricule: str = Depends(get_current_user)):
    """Récupère les informations d'identité de l'utilisateur connecté."""
    user = MOCK_DB["users"][matricule]
    # Return user info without password
    return {k: v for k, v in user.items() if k != "password"}

# Dossiers
@app.get("/api/v1/adherent/dossiers", tags=["Métier"])
async def get_dossiers(matricule: str = Depends(get_current_user)):
    """Liste les dossiers médicaux ou administratifs de l'utilisateur connecté."""
    return MOCK_DB["dossiers"].get(matricule, [])

# Beneficiaires
@app.get("/api/v1/adherent/beneficiaires", tags=["Métier"])
async def get_beneficiaires(matricule: str = Depends(get_current_user)):
    """Récupère la liste des personnes couvertes (conjoint, enfants)."""
    return MOCK_DB["beneficiaires"].get(matricule, [])

# Prestations
@app.get("/api/v1/prestations", tags=["Métier"])
async def get_prestations(matricule: str = Depends(get_current_user)):
    """Détail technique des actes médicaux effectués."""
    return MOCK_DB["prestations"].get(matricule, [])

# Remboursements
@app.get("/api/v1/remboursements", tags=["Métier"])
async def get_remboursements(matricule: str = Depends(get_current_user)):
    """Historique financier des virements effectués."""
    return MOCK_DB["remboursements"].get(matricule, [])

# Réclamations – list
@app.get("/api/v1/reclamations", tags=["Support"])
async def get_reclamations_history(matricule: str = Depends(get_current_user)):
    """Liste l'historique complet des tickets de support."""
    return MOCK_DB["reclamations"].get(matricule, [])

# Réclamations – create
@app.post("/api/v1/reclamations", tags=["Support"])
async def create_reclamation(data: ReclamationInput, matricule: str = Depends(get_current_user)):
    """Soumission d'un formulaire simple de réclamation."""
    if SIMULATE_LATENCY:
        time.sleep(1)

    new_ticket = {
        "id": f"TICKET-{uuid.uuid4().hex[:6].upper()}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objet": data.objet,
        "statut": "Ouvert",
        "message_preview": data.message[:50] + "..."
    }

    if data.matricule not in MOCK_DB["reclamations"]:
        MOCK_DB["reclamations"][data.matricule] = []
    MOCK_DB["reclamations"][data.matricule].append(new_ticket)

    logger.info(f"📩 New Reclamation from {data.matricule}: {data.objet}")
    return {"status": "success", "ticket": new_ticket}

# Escalation
@app.post("/api/v1/support/escalade", tags=["Support"])
async def escalate_to_human(data: EscaladeInput, matricule: str = Depends(get_current_user)):
    """Endpoint critique pour l'envoi vers un agent humain."""
    logger.warning(f"🚨 ESCALATION TRIGGERED for {data.matricule}")
    logger.info(f"Context size: {len(data.chat_history)} messages")

    user = MOCK_DB["users"].get(data.matricule, {})
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

    MOCK_DB["escalation_tickets"].append(ticket)

    return {
        "status": "escalated",
        "queue_position": ticket["queue_position"],
        "estimated_wait": ticket["estimated_wait"],
        "case_id": ticket["case_id"]
    }

# Dashboard endpoint – list all escalation tickets (for the React dashboard in Step 3)
@app.get("/api/v1/dashboard/tickets", tags=["Dashboard"])
async def get_escalation_tickets(matricule: str = Depends(get_current_user)):
    """Returns all open escalation tickets for the agent dashboard."""
    return MOCK_DB["escalation_tickets"]


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 I-Way Digital Twin is starting...")
    print(f"   Persona 1 (Adherent):     matricule=12345  password=pass")
    print(f"   Persona 2 (Prestataire):  matricule=99999  password=med")
    print(f"   Docs available at: http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)