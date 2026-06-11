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
import bcrypt

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


def init_keys(keys_dir: str) -> bool:
    """Load the RSA keypair from disk, generating + persisting it on first run.

    Persisting the keypair means an API restart no longer invalidates every
    live JWT (previously keys were regenerated per process, logging everyone
    out mid-conversation on each deploy/reload).

    Returns True if the key was loaded from disk, False if freshly generated.
    """
    from pathlib import Path
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    key_dir = Path(keys_dir)
    key_path = key_dir / "jwt_private.pem"

    if key_path.exists():
        auth_state.private_key = serialization.load_pem_private_key(
            key_path.read_bytes(), password=None,
        )
        loaded = True
    else:
        key_dir.mkdir(parents=True, exist_ok=True)
        auth_state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_path.write_bytes(auth_state.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        try:  # best-effort: restrict to owner (POSIX only — no-op on Windows)
            key_path.chmod(0o600)
        except Exception:
            pass
        loaded = False

    auth_state.public_key_pem = auth_state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return loaded


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
        "password_hash": "$2b$12$fy/C8bpfRtYvcJQfpWnrR.9zf2TEjsSSjlOR0cVz7OE6rGjifC7yO"  # pass
    },
    "99999": {
        "matricule": "99999", "nom": "Zaid", "prenom": "Amine",
        "role": "Prestataire", "email": "amine.zaid@clinique.tn",
        "specialite": "Cardiologie", "password_hash": "$2b$12$MTxw/2PzzC5YloiWOfduDuvgK79.E8q.tcLduY.pCxuR0CvvwMaQu"  # med
    },
    "88888": {
        "matricule": "88888", "nom": "Belhadj", "prenom": "Karim",
        "role": "Agent", "email": "karim.belhadj@iway.tn",
        "password_hash": "$2b$12$dp29PQKJJ82TU0WmxL3aCOufQEuIpkVBANGbxlhsOdiSBmUI3yyhS"  # agent
    },
    "77777": {
        "matricule": "77777", "nom": "Toumi", "prenom": "Sara",
        "role": "Admin", "email": "sara.toumi@iway.tn",
        "password_hash": "$2b$12$tvH8jRLIQsweJKLtOmFk0eqcTbniIQExBlTVo9NAd8BURZbNcCDOy"  # admin
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


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: verifies the user has one of the allowed roles.
    
    Usage:
        @router.get("/admin/config")
        async def admin_config(matricule: str = Depends(require_role("Admin"))):
            ...
    """
    async def _check_role(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
        payload = verify_jwt(credentials.credentials)
        matricule = payload.get("sub")
        user = MOCK_USERS.get(matricule)
        if not user:
            raise HTTPException(status_code=403, detail="User not found")
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user['role']}' not authorized. Required: {list(allowed_roles)}"
            )
        return matricule
    return _check_role


# --- Endpoints ---

@router.post("/login")
async def login(data: LoginInput):
    """Authenticate with matricule + password, receive an RS256-signed JWT."""
    user = MOCK_USERS.get(data.matricule)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid matricule or password")
        
    password_valid = bcrypt.checkpw(data.password.encode('utf-8'), user["password_hash"].encode('utf-8'))
    if not password_valid:
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


@router.post("/refresh")
async def refresh_token(matricule: str = Depends(get_current_user)):
    """Sliding-session renewal: exchange a valid (non-expired) token for a fresh one.

    Lets the frontend renew before expiry instead of dropping the user to the
    login screen mid-conversation.
    """
    token = create_jwt(matricule)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
    }


@router.get("/public-key")
async def get_public_key():
    """Expose the RSA public key (PEM) for external JWT verification."""
    return {
        "algorithm": settings.JWT_ALGORITHM,
        "public_key": auth_state.public_key_pem.decode("utf-8")
    }
