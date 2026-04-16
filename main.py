import os
import json
import time
import uuid
import random
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

# Third-party imports
from fastapi import FastAPI, HTTPException, Depends, Header, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
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

# CORS — allow Angular dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4201"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        },
        "88888": {
            "matricule": "88888",
            "nom": "Belhadj",
            "prenom": "Karim",
            "role": "Agent",
            "password": "agent"
        },
        "77777": {
            "matricule": "77777",
            "nom": "Toumi",
            "prenom": "Sara",
            "role": "Admin",
            "password": "admin"
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
    "escalation_tickets": [],
    # System interaction logs
    "system_logs": [
        {"id": "L001", "timestamp": "2026-04-13 19:07:12", "user_id": "12345", "query": "Comment ajouter un beneficiaire ?", "top_similarity": 0.94, "chunks_retrieved": 3, "gen_time_ms": 820, "tokens_used": 842, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 94},
        {"id": "L002", "timestamp": "2026-04-13 19:06:55", "user_id": "12345", "query": "Quel est le delai de remboursement ?", "top_similarity": 0.88, "chunks_retrieved": 3, "gen_time_ms": 750, "tokens_used": 921, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 88},
        {"id": "L003", "timestamp": "2026-04-13 19:05:30", "user_id": "99999", "query": "Comment facturer un acte hors nomenclature ?", "top_similarity": 0.71, "chunks_retrieved": 2, "gen_time_ms": 1140, "tokens_used": 1203, "outcome": "AI_FALLBACK", "model": "gemini-2.5-flash", "confidence": 71},
        {"id": "L004", "timestamp": "2026-04-13 19:04:01", "user_id": "12345", "query": "Je veux parler a un humain", "top_similarity": 0.38, "chunks_retrieved": 1, "gen_time_ms": 2310, "tokens_used": 1842, "outcome": "HUMAN_ESCALATED", "model": "gemini-2.5-flash", "confidence": 38},
        {"id": "L005", "timestamp": "2026-04-13 19:03:44", "user_id": "12345", "query": "Prise en charge hospitaliere urgence", "top_similarity": 0.96, "chunks_retrieved": 3, "gen_time_ms": 610, "tokens_used": 703, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 96},
        {"id": "L006", "timestamp": "2026-04-13 19:02:18", "user_id": "99999", "query": "Erreur de connexion au portail prestataire", "top_similarity": 0.29, "chunks_retrieved": 1, "gen_time_ms": 3100, "tokens_used": 2102, "outcome": "ERROR", "model": "gemini-2.5-flash", "confidence": 15},
        {"id": "L007", "timestamp": "2026-04-13 19:01:05", "user_id": "12345", "query": "Quel est le plafond pour les soins dentaires ?", "top_similarity": 0.92, "chunks_retrieved": 3, "gen_time_ms": 690, "tokens_used": 780, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 92},
        {"id": "L008", "timestamp": "2026-04-13 19:00:22", "user_id": "12345", "query": "Quelle est la prime de naissance ?", "top_similarity": 0.91, "chunks_retrieved": 3, "gen_time_ms": 870, "tokens_used": 910, "outcome": "RAG_RESOLVED", "model": "gemini-2.5-flash", "confidence": 91},
    ],
    # System configuration
    "system_config": {
        "rag": {
            "chunking_strategy": "semantic",
            "top_k": 3,
            "similarity_threshold": 82,
            "enable_ai_fallback": True,
            "auto_escalate_negative_sentiment": True,
        },
        "llm": {
            "primary_model": "gemini-2.5-flash",
            "temperature": 0.2,
            "system_prompt": "Tu es l'assistant virtuel I-Sante...",
        },
        "retry": {
            "max_retries": 3,
            "backoff_seconds": 2,
        },
    },
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
    user = MOCK_DB["users"].get(matricule, {})
    payload = {
        "sub": matricule,
        "role": user.get("role", "Adherent"),
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
            "role": user["role"],
            "email": user.get("email", ""),
            "specialite": user.get("specialite", "")
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


# --- 9. MONITORING & ANALYTICS ENDPOINTS ---

@app.get("/api/v1/metrics", tags=["Monitoring"])
async def get_metrics(matricule: str = Depends(get_current_user)):
    """Aggregated dashboard metrics for the monitoring UI."""
    logs = MOCK_DB["system_logs"]
    total = len(logs)
    rag_resolved = sum(1 for l in logs if l["outcome"] == "RAG_RESOLVED")
    ai_fallback = sum(1 for l in logs if l["outcome"] == "AI_FALLBACK")
    human_escalated = sum(1 for l in logs if l["outcome"] == "HUMAN_ESCALATED")
    errors = sum(1 for l in logs if l["outcome"] == "ERROR")
    avg_confidence = round(sum(l["confidence"] for l in logs) / max(total, 1), 1)
    avg_response_time = round(sum(l["gen_time_ms"] for l in logs) / max(total, 1))

    return {
        "total_requests": total,
        "rag_resolved": rag_resolved,
        "ai_fallback": ai_fallback,
        "human_escalated": human_escalated,
        "errors": errors,
        "avg_confidence": avg_confidence,
        "avg_response_time_ms": avg_response_time,
        "rag_success_rate": round(rag_resolved / max(total, 1) * 100, 1),
        "fallback_rate": round(ai_fallback / max(total, 1) * 100, 1),
        "escalation_rate": round(human_escalated / max(total, 1) * 100, 1),
        "error_rate": round(errors / max(total, 1) * 100, 1),
        "open_tickets": len(MOCK_DB["escalation_tickets"]),
        "time_series": [
            {"day": "Mon", "rag_confidence": 82, "response_time": 120, "requests": 180},
            {"day": "Tue", "rag_confidence": 85, "response_time": 132, "requests": 210},
            {"day": "Wed", "rag_confidence": 79, "response_time": 101, "requests": 195},
            {"day": "Thu", "rag_confidence": 88, "response_time": 134, "requests": 230},
            {"day": "Fri", "rag_confidence": 92, "response_time": 90, "requests": 245},
            {"day": "Sat", "rag_confidence": 89, "response_time": 110, "requests": 160},
            {"day": "Sun", "rag_confidence": 90, "response_time": 105, "requests": 140},
        ]
    }


@app.get("/api/v1/logs", tags=["Monitoring"])
async def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    outcome: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_similarity: Optional[float] = Query(None, ge=0, le=1),
    matricule: str = Depends(get_current_user),
):
    """Paginated system interaction logs with filters."""
    logs = MOCK_DB["system_logs"]

    if outcome:
        logs = [l for l in logs if l["outcome"] == outcome]
    if user_id:
        logs = [l for l in logs if l["user_id"] == user_id]
    if search:
        q = search.lower()
        logs = [l for l in logs if q in l["query"].lower() or q in l["user_id"].lower()]
    if min_similarity is not None:
        logs = [l for l in logs if l["top_similarity"] >= min_similarity]

    total = len(logs)
    start = (page - 1) * page_size
    page_logs = logs[start:start + page_size]

    return {
        "items": page_logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@app.get("/api/v1/insights", tags=["Analytics"])
async def get_insights(matricule: str = Depends(get_current_user)):
    """AI-generated insights about knowledge base gaps and RAG performance."""
    logs = MOCK_DB["system_logs"]
    failed = [l for l in logs if l["outcome"] in ("AI_FALLBACK", "HUMAN_ESCALATED", "ERROR")]
    rag_resolved = [l for l in logs if l["outcome"] == "RAG_RESOLVED"]

    return {
        "knowledge_gaps": 23,
        "rag_coverage_rate": round(len(rag_resolved) / max(len(logs), 1) * 100),
        "docs_suggested": 142,
        "failed_clusters": 18,
        "suggestions": [
            {"category": "Facturation Hors Nomenclature", "count": 342, "trend": "up", "trend_pct": 28, "priority": "high", "suggestion": "Creer des docs detailles couvrant les flux de facturation HN, les codes d'actes speciaux et les procedures d'accord prealable."},
            {"category": "Conformite RGPD", "count": 287, "trend": "up", "trend_pct": 15, "priority": "high", "suggestion": "Developper la section conformite avec les workflows de suppression en masse et les modeles DPA."},
            {"category": "Configuration SSO Entreprise", "count": 214, "trend": "stable", "trend_pct": 2, "priority": "high", "suggestion": "Ajouter des guides pas-a-pas pour la configuration SAML avec Active Directory et Google Workspace."},
            {"category": "Erreurs Webhook", "count": 178, "trend": "up", "trend_pct": 8, "priority": "medium", "suggestion": "Documenter les modes de defaillance courants des webhooks (SSL, timeout, logique de retry) avec des exemples de code."},
            {"category": "Import CSV Cas Limites", "count": 156, "trend": "down", "trend_pct": 5, "priority": "medium", "suggestion": "Enrichir la documentation d'import CSV pour couvrir les problemes d'encodage et les limites de lignes."},
            {"category": "Configuration DNS White-Label", "count": 98, "trend": "stable", "trend_pct": 1, "priority": "low", "suggestion": "Creer un guide reseau couvrant la configuration de domaine personnalise avec provisionnement SSL."},
        ],
        "fallback_categories": [
            {"name": "DNS White-Label", "count": 98},
            {"name": "Import CSV", "count": 156},
            {"name": "Erreurs Webhook", "count": 178},
            {"name": "Config SSO", "count": 214},
            {"name": "RGPD", "count": 287},
            {"name": "Auth API", "count": 342},
        ],
        "confidence_distribution": [
            {"range": "0-0.1", "count": 42}, {"range": "0.1-0.2", "count": 78},
            {"range": "0.2-0.3", "count": 120}, {"range": "0.3-0.4", "count": 180},
            {"range": "0.4-0.5", "count": 210}, {"range": "0.5-0.6", "count": 390},
            {"range": "0.6-0.7", "count": 580}, {"range": "0.7-0.8", "count": 920},
            {"range": "0.8-0.9", "count": 1840}, {"range": "0.9-1.0", "count": 3100},
        ],
    }


@app.get("/api/v1/admin/config", tags=["Admin"])
async def get_admin_config(matricule: str = Depends(get_current_user)):
    """Get current system configuration."""
    return MOCK_DB["system_config"]


class ConfigUpdate(BaseModel):
    rag: Optional[Dict[str, Any]] = None
    llm: Optional[Dict[str, Any]] = None
    retry: Optional[Dict[str, Any]] = None


@app.put("/api/v1/admin/config", tags=["Admin"])
async def update_admin_config(data: ConfigUpdate, matricule: str = Depends(get_current_user)):
    """Update system configuration."""
    if data.rag:
        MOCK_DB["system_config"]["rag"].update(data.rag)
    if data.llm:
        MOCK_DB["system_config"]["llm"].update(data.llm)
    if data.retry:
        MOCK_DB["system_config"]["retry"].update(data.retry)
    logger.info(f"Config updated by {matricule}")
    return {"status": "updated", "config": MOCK_DB["system_config"]}


# --- 10. WEBSOCKET ENDPOINT & SESSION MANAGEMENT ---

# In-memory session store for HITL chat sessions
SESSIONS: Dict[str, Dict[str, Any]] = {}

class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()


# --- Helper: Simulated AI response for chat ---
def get_simulated_ai_response(query: str) -> dict:
    """Returns a simulated RAG/AI response with confidence score."""
    q = query.lower()
    responses = {
        "dentaire": ("Selon l'Article 4, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire.", 94),
        "remboursement": ("Les remboursements sont traites sous 48h ouvrees pour les FSE. Les feuilles papier: 15 jours ouvres.", 88),
        "naissance": ("La prime de naissance est de 300 TND par enfant, versee sur presentation de l'acte de naissance.", 91),
        "urgence": ("En cas d'urgence, les frais sont pris en charge a 100%. Numero d'urgence I-Way: 71 800 800.", 96),
        "humain": (None, 15),  # Triggers handoff
        "agent": (None, 20),   # Triggers handoff
        "parler": (None, 18),  # Triggers handoff
    }
    for keyword, (text, confidence) in responses.items():
        if keyword in q:
            return {"text": text, "confidence": confidence}
    return {
        "text": "D'apres la base de connaissances I-Way, je vous recommande de consulter votre espace adherent ou de contacter notre service client au 71 800 800.",
        "confidence": 72
    }


# --- Session REST Endpoints ---

@app.post("/api/v1/sessions/create", tags=["Sessions"])
async def create_session(matricule: str = Depends(get_current_user)):
    """Create a new chat session for a user."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    user = MOCK_DB["users"].get(matricule, {})
    SESSIONS[session_id] = {
        "id": session_id,
        "user_matricule": matricule,
        "user_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
        "user_role": user.get("role", "Unknown"),
        "status": "active",  # active | handoff_pending | agent_connected | resolved
        "history": [],
        "created_at": datetime.now().isoformat(),
        "agent_matricule": None,
        "user_ws": None,
        "agent_ws": None,
        "reason": None,
    }
    logger.info(f"Session created: {session_id} for {matricule}")
    return {"session_id": session_id}


@app.get("/api/v1/sessions/active", tags=["Sessions"])
async def get_active_sessions(matricule: str = Depends(get_current_user)):
    """List all active/pending sessions for the agent queue."""
    active = []
    for sid, s in SESSIONS.items():
        if s["status"] in ("active", "handoff_pending", "agent_connected"):
            active.append({
                "id": s["id"],
                "user_matricule": s["user_matricule"],
                "user_name": s["user_name"],
                "user_role": s["user_role"],
                "status": s["status"],
                "created_at": s["created_at"],
                "reason": s["reason"],
                "message_count": len(s["history"]),
                "last_message": s["history"][-1]["content"][:80] if s["history"] else "",
                "agent_matricule": s["agent_matricule"],
            })
    # Sort: handoff_pending first, then by creation time
    priority = {"handoff_pending": 0, "active": 1, "agent_connected": 2}
    active.sort(key=lambda x: (priority.get(x["status"], 9), x["created_at"]))
    return active


@app.get("/api/v1/sessions/{session_id}/history", tags=["Sessions"])
async def get_session_history(session_id: str, matricule: str = Depends(get_current_user)):
    """Get full chat history for a session."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session["status"],
        "user_name": session["user_name"],
        "user_role": session["user_role"],
        "user_matricule": session["user_matricule"],
        "created_at": session["created_at"],
        "agent_matricule": session["agent_matricule"],
        "reason": session["reason"],
        "history": session["history"],
    }


@app.post("/api/v1/sessions/{session_id}/takeover", tags=["Sessions"])
async def takeover_session(session_id: str, matricule: str = Depends(get_current_user)):
    """Agent takes over a session."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    user = MOCK_DB["users"].get(matricule, {})
    session["status"] = "agent_connected"
    session["agent_matricule"] = matricule
    agent_name = f"{user.get('prenom', '')} {user.get('nom', '')}".strip()
    # Add system message to history
    session["history"].append({
        "role": "system",
        "content": f"Agent {agent_name} a rejoint la conversation.",
        "timestamp": datetime.now().isoformat()
    })
    # Notify the user via their WebSocket if connected
    user_ws = session.get("user_ws")
    if user_ws:
        try:
            await user_ws.send_json({"type": "agent_joined", "agent_name": agent_name})
        except Exception:
            pass
    # Broadcast to agent event stream
    await ws_manager.broadcast({"type": "AGENT_JOINED", "payload": {"session_id": session_id, "agent": agent_name}})
    logger.info(f"Agent {matricule} took over session {session_id}")
    return {"status": "taken_over", "session_id": session_id}


@app.post("/api/v1/sessions/{session_id}/resolve", tags=["Sessions"])
async def resolve_session(session_id: str, matricule: str = Depends(get_current_user)):
    """Mark a session as resolved."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["status"] = "resolved"
    session["history"].append({
        "role": "system",
        "content": "Session resolue par l'agent.",
        "timestamp": datetime.now().isoformat()
    })
    user_ws = session.get("user_ws")
    if user_ws:
        try:
            await user_ws.send_json({"type": "session_resolved"})
        except Exception:
            pass
    await ws_manager.broadcast({"type": "SESSION_RESOLVED", "payload": {"session_id": session_id}})
    logger.info(f"Session {session_id} resolved by {matricule}")
    return {"status": "resolved"}


# --- Admin/Agent events WebSocket ---

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard/agent updates.
    Sends periodic metric snapshots and broadcasts escalation events."""
    await ws_manager.connect(websocket)
    try:
        while True:
            logs = MOCK_DB["system_logs"]
            total = len(logs)
            rag_resolved = sum(1 for l in logs if l["outcome"] == "RAG_RESOLVED")
            pending_sessions = sum(1 for s in SESSIONS.values() if s["status"] == "handoff_pending")
            await websocket.send_json({
                "type": "METRIC_UPDATE",
                "payload": {
                    "total_requests": total,
                    "rag_resolved": rag_resolved,
                    "ai_fallback": sum(1 for l in logs if l["outcome"] == "AI_FALLBACK"),
                    "human_escalated": sum(1 for l in logs if l["outcome"] == "HUMAN_ESCALATED"),
                    "errors": sum(1 for l in logs if l["outcome"] == "ERROR"),
                    "open_tickets": len(MOCK_DB["escalation_tickets"]),
                    "pending_handoffs": pending_sessions,
                    "active_sessions": len([s for s in SESSIONS.values() if s["status"] != "resolved"]),
                    "timestamp": datetime.now().isoformat(),
                }
            })
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# --- Per-session chat WebSocket ---

@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """Per-session WebSocket for user/agent chat.
    Handles user messages, AI responses, handoff, and agent relay."""
    session = SESSIONS.get(session_id)
    if not session:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    # Determine if this is user or agent connection based on query param
    # Default: user connection. Agent sends {type: "agent_connect"} as first message.
    is_agent = False

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "agent_connect":
                # Agent identifying themselves on this session WS
                is_agent = True
                session["agent_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "agent", "session_id": session_id})
                continue

            if msg_type == "user_connect":
                session["user_ws"] = websocket
                await websocket.send_json({"type": "connected", "role": "user", "session_id": session_id})
                # Send history so far
                await websocket.send_json({"type": "history", "messages": session["history"]})
                continue

            if msg_type == "user_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                # Add to history
                user_msg = {"role": "user", "content": content, "timestamp": datetime.now().isoformat()}
                session["history"].append(user_msg)

                if session["status"] == "agent_connected":
                    # Relay to agent
                    agent_ws = session.get("agent_ws")
                    if agent_ws:
                        try:
                            await agent_ws.send_json({"type": "user_message", "content": content, "timestamp": user_msg["timestamp"]})
                        except Exception:
                            pass
                else:
                    # AI response flow
                    await websocket.send_json({"type": "thinking"})
                    await asyncio.sleep(1.0 + random.random())  # Simulate processing
                    ai_result = get_simulated_ai_response(content)

                    if ai_result["confidence"] < 30 or ai_result["text"] is None:
                        # Auto handoff — low confidence
                        session["status"] = "handoff_pending"
                        session["reason"] = f"Low confidence ({ai_result['confidence']}%) on: {content[:50]}"
                        session["history"].append({
                            "role": "system",
                            "content": "Transfert vers un specialiste I-Way en cours...",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({"type": "handoff_started", "reason": session["reason"]})
                        # Broadcast to agent queue
                        await ws_manager.broadcast({
                            "type": "NEW_ESCALATION",
                            "payload": {
                                "session_id": session_id,
                                "user_name": session["user_name"],
                                "user_role": session["user_role"],
                                "reason": session["reason"],
                                "created_at": session["created_at"],
                            }
                        })
                    else:
                        # Stream AI response token by token
                        response_text = ai_result["text"]
                        words = response_text.split(" ")
                        for i, word in enumerate(words):
                            token = word + (" " if i < len(words) - 1 else "")
                            await websocket.send_json({"type": "ai_token", "token": token})
                            await asyncio.sleep(0.03 + random.random() * 0.05)
                        await websocket.send_json({"type": "ai_done", "confidence": ai_result["confidence"]})
                        session["history"].append({
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": datetime.now().isoformat(),
                            "confidence": ai_result["confidence"]
                        })

            elif msg_type == "agent_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                agent_msg = {"role": "agent", "content": content, "timestamp": datetime.now().isoformat()}
                session["history"].append(agent_msg)
                # Relay to user
                user_ws = session.get("user_ws")
                if user_ws:
                    try:
                        await user_ws.send_json({"type": "agent_message", "content": content, "timestamp": agent_msg["timestamp"]})
                    except Exception:
                        pass

            elif msg_type == "manual_handoff_request":
                session["status"] = "handoff_pending"
                session["reason"] = "User manually requested a human agent"
                session["history"].append({
                    "role": "system",
                    "content": "Vous avez demande a parler a un agent humain. Transfert en cours...",
                    "timestamp": datetime.now().isoformat()
                })
                await websocket.send_json({"type": "handoff_started", "reason": session["reason"]})
                await ws_manager.broadcast({
                    "type": "NEW_ESCALATION",
                    "payload": {
                        "session_id": session_id,
                        "user_name": session["user_name"],
                        "user_role": session["user_role"],
                        "reason": session["reason"],
                        "created_at": session["created_at"],
                    }
                })

            elif msg_type == "PING":
                await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        if is_agent:
            session["agent_ws"] = None
        else:
            session["user_ws"] = None
        logger.info(f"Chat WS disconnected from session {session_id} (agent={is_agent})")
    except Exception as e:
        logger.error(f"Chat WS error in session {session_id}: {e}")
        if is_agent:
            session["agent_ws"] = None
        else:
            session["user_ws"] = None


if __name__ == "__main__":
    import uvicorn
    print("\n[INFO] I-Way Digital Twin is starting...")
    print(f"   Persona 1 (Adherent):     matricule=12345  password=pass")
    print(f"   Persona 2 (Prestataire):  matricule=99999  password=med")
    print(f"   Docs available at: http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)