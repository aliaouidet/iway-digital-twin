"""
Auth Router — Login, JWT generation/verification, public key exposure.

Preserves the existing API contracts:
  POST /auth/login
  GET  /auth/public-key
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt  # PyJWT

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Auth"])
bearer_scheme = HTTPBearer()


# --- Shared State (RSA keys — set by main.py at startup) ---
class AuthState:
    private_key = None
    public_key_pem = None

auth_state = AuthState()


# --- Pydantic Models ---
class LoginInput(BaseModel):
    matricule: str
    password: str


# --- Mock I-Way User Database (simulates I-Way's auth API) ---
# In production, this would call I-Way's authentication endpoint
MOCK_USERS = {
    "12345": {
        "matricule": "12345", "nom": "Mansour", "prenom": "Nadia",
        "role": "Adherent", "email": "nadia.mansour@email.com",
        "password": "pass"
    },
    "99999": {
        "matricule": "99999", "nom": "Zaid", "prenom": "Amine",
        "role": "Prestataire", "email": "amine.zaid@clinique.tn",
        "specialite": "Cardiologie", "password": "med"
    },
    "88888": {
        "matricule": "88888", "nom": "Belhadj", "prenom": "Karim",
        "role": "Agent", "email": "karim.belhadj@iway.tn",
        "password": "agent"
    },
    "77777": {
        "matricule": "77777", "nom": "Toumi", "prenom": "Sara",
        "role": "Admin", "email": "sara.toumi@iway.tn",
        "password": "admin"
    },
}


# --- JWT Creation & Verification ---

def create_jwt(matricule: str) -> str:
    """Create an RS256-signed JWT for the given matricule."""
    user = MOCK_USERS.get(matricule, {})
    from cryptography.hazmat.primitives import serialization
    payload = {
        "sub": matricule,
        "role": user.get("role", "Adherent"),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
        "iss": "i-way-digital-twin"
    }
    private_key_pem = auth_state.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return jwt.encode(payload, private_key_pem, algorithm=settings.JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Verify and decode an RS256 JWT."""
    try:
        payload = jwt.decode(
            token,
            auth_state.public_key_pem,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="i-way-digital-twin"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """FastAPI dependency: extracts Bearer token, verifies, returns matricule."""
    payload = verify_jwt(credentials.credentials)
    matricule = payload.get("sub")
    if matricule not in MOCK_USERS:
        raise HTTPException(status_code=403, detail="User not found in Simulator DB")
    return matricule


# --- Endpoints ---

@router.post("/login")
async def login(data: LoginInput):
    """Authenticate with matricule + password, receive an RS256-signed JWT."""
    user = MOCK_USERS.get(data.matricule)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid matricule or password")

    token = create_jwt(data.matricule)
    logger.info(f"🔑 Login successful for {data.matricule} ({user['prenom']} {user['nom']})")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
        "user": {
            "matricule": user["matricule"],
            "nom": user["nom"],
            "prenom": user["prenom"],
            "role": user["role"],
            "email": user.get("email", ""),
            "specialite": user.get("specialite", "")
        }
    }


@router.get("/public-key")
async def get_public_key():
    """Expose the RSA public key (PEM) for external JWT verification."""
    return {
        "algorithm": settings.JWT_ALGORITHM,
        "public_key": auth_state.public_key_pem.decode("utf-8")
    }
