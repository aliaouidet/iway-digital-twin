"""
Auth Router — Login, activation, JWT generation/verification, public key exposure.

API contracts:
  POST /auth/login        — demo personas (MOCK_USERS) OR activated ERP users
  POST /auth/activate     — first-login identity verification against the real
                            ERP (adhérent), sets a local password   [real mode]
  POST /auth/activate-ps  — same for prestataires (matricule fiscal) [real mode]
  POST /auth/refresh      — sliding-session renewal (claims preserved)
  GET  /auth/public-key

Real-auth design (the ERP exposes NO login operation): activation verifies the
claimed identity against contratAdherentWSMeg/contratPsWS (DOB or CIN must
match), then stores a bcrypt password in OUR users table (source='erp'). Later
logins check that local password — no LAN required after activation.
"""

import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional

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


class ActivateInput(BaseModel):
    """First-login activation (adhérent): identity claim verified against the ERP."""
    matricule: str
    num_police: str
    date_naissance: Optional[str] = None  # YYYY-MM-DD
    cin: Optional[str] = None
    new_password: str


class ActivatePsInput(BaseModel):
    """First-login activation (prestataire): matricule fiscal → idTiers → identity."""
    matricule_fiscal: str
    nom_verification: str          # raison sociale / nom as registered with I-Way
    new_password: str


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


# --- User resolution (demo personas + activated ERP users) ---

async def resolve_user(matricule: str) -> Optional[dict]:
    """Resolve a matricule to the canonical user dict shape.

    Order: MOCK_USERS (demo personas, no DB needed) → users table (activated
    ERP users, source='erp'). Returns None when unknown. This is the ONE lookup
    every consumer should use instead of reading MOCK_USERS directly — real
    users would otherwise be invisible (403s, 'Unknown' names) outside demos.
    """
    user = MOCK_USERS.get(matricule)
    if user:
        return user
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import get_user

        async with async_session_factory() as db:
            row = await get_user(db, matricule)
        if row is None:
            return None
        return {
            "matricule": row.matricule,
            "nom": row.nom,
            "prenom": row.prenom,
            "role": row.role.value if hasattr(row.role, "value") else str(row.role),
            "email": row.email or "",
            "specialite": row.specialite or "",
            "password_hash": row.password_hash,
            "num_police": row.num_police or "",
            "id_tiers": row.id_tiers or "",
            "source": row.source,
        }
    except Exception as e:
        logger.warning(f"⚠️ resolve_user({matricule}) DB lookup failed: {e}")
        return None


# --- JWT Creation & Verification ---

def create_jwt(
    matricule: str,
    role: Optional[str] = None,
    num_police: str = "",
    id_tiers: str = "",
) -> str:
    """Create an RS256-signed JWT.

    ``num_police``/``id_tiers`` ride as claims so real-mode SOAP lookups (which
    REQUIRE numPolice) get them without a DB round-trip per message. When
    ``role`` is omitted, falls back to the demo persona's role (legacy call sites).
    """
    user = MOCK_USERS.get(matricule, {})
    from cryptography.hazmat.primitives import serialization
    payload = {
        "sub": matricule,
        "role": role or user.get("role", "Adherent"),
        "num_police": num_police or user.get("num_police", ""),
        "id_tiers": id_tiers or user.get("id_tiers", ""),
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
    """FastAPI dependency: extracts Bearer token, verifies, returns matricule.

    The RS256 signature is the trust anchor — a token can only exist for users
    we authenticated (demo persona or activated ERP user), so no membership
    check against MOCK_USERS (that 403'd every real user).
    """
    payload = verify_jwt(credentials.credentials)
    matricule = payload.get("sub")
    if not matricule:
        raise HTTPException(status_code=401, detail="Token missing subject")
    return matricule


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: verifies the user has one of the allowed roles.

    The role comes from the VERIFIED token's claim (set at login from the user
    record) — not from MOCK_USERS, which doesn't know activated ERP users.

    Usage:
        @router.get("/admin/config")
        async def admin_config(matricule: str = Depends(require_role("Admin"))):
            ...
    """
    async def _check_role(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
        payload = verify_jwt(credentials.credentials)
        matricule = payload.get("sub")
        role = payload.get("role", "")
        if not matricule:
            raise HTTPException(status_code=401, detail="Token missing subject")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' not authorized. Required: {list(allowed_roles)}"
            )
        return matricule
    return _check_role


# --- Activation rate limit (in-memory, per matricule) ---
# The DOB/CIN challenge is brute-forceable without this. Process-local is fine:
# the surface is one on-prem deployment, and the circuit breaker bounds total
# ERP traffic anyway.
_ACTIVATION_ATTEMPTS: dict = {}  # {matricule: [monotonic_ts, ...]}
_ACTIVATION_MAX_ATTEMPTS = 5
_ACTIVATION_WINDOW_S = 15 * 60


def _activation_rate_limited(matricule: str) -> bool:
    now = _time.monotonic()
    attempts = [t for t in _ACTIVATION_ATTEMPTS.get(matricule, []) if now - t < _ACTIVATION_WINDOW_S]
    _ACTIVATION_ATTEMPTS[matricule] = attempts
    if len(attempts) >= _ACTIVATION_MAX_ATTEMPTS:
        return True
    attempts.append(now)
    return False


def _norm_date(value) -> str:
    """Normalize '1985-06-12', '1985-06-12 00:00:00', datetime → 'YYYY-MM-DD'."""
    import re as _re
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    return m.group(0) if m else ""


def _login_response(token: str, user: dict) -> dict:
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
        "user": {
            "matricule": user["matricule"],
            "nom": user["nom"],
            "prenom": user.get("prenom", ""),
            "role": user["role"],
            "email": user.get("email", ""),
            "specialite": user.get("specialite", "")
        }
    }


# --- Endpoints ---

@router.post("/login")
async def login(data: LoginInput):
    """Authenticate with matricule + password, receive an RS256-signed JWT.

    Demo personas (MOCK_USERS) take priority — byte-for-byte legacy behavior.
    On miss, falls back to the users table (ERP users created by /auth/activate);
    that path needs no LAN, only our Postgres.
    """
    user = MOCK_USERS.get(data.matricule)
    if not user:
        resolved = await resolve_user(data.matricule)
        user = resolved if resolved and resolved.get("source") == "erp" else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid matricule or password")

    password_valid = bcrypt.checkpw(data.password.encode('utf-8'), user["password_hash"].encode('utf-8'))
    if not password_valid:
        raise HTTPException(status_code=401, detail="Invalid matricule or password")

    token = create_jwt(
        data.matricule,
        role=user["role"],
        num_police=user.get("num_police", ""),
        id_tiers=user.get("id_tiers", ""),
    )
    if user.get("source") == "erp":
        try:
            from backend.database.connection import async_session_factory
            from backend.database.repositories import touch_last_login
            async with async_session_factory() as db:
                await touch_last_login(db, data.matricule)
                await db.commit()
        except Exception:  # best-effort bookkeeping
            pass
    logger.info(f"🔑 Login successful for {data.matricule} ({user.get('prenom', '')} {user['nom']})")
    return _login_response(token, user)


@router.post("/activate")
async def activate_account(data: ActivateInput):
    """First-login activation (adhérent) — REAL MODE ONLY.

    Verifies the claimed identity against the live ERP
    (getContratAdherentByMatricule → DOB or CIN must match), then stores a
    bcrypt password in the users table and returns a normal login response.
    Re-activation of an existing account doubles as password reset (identity is
    re-verified each time).
    """
    if not settings.IWAY_USE_REAL_API:
        raise HTTPException(
            status_code=400,
            detail="Activation indisponible en mode démo — utilisez un compte de démonstration.",
        )
    if not data.date_naissance and not data.cin:
        raise HTTPException(
            status_code=400,
            detail="La date de naissance ou le numéro de CIN est nécessaire pour vérifier votre identité.",
        )
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères.")
    if _activation_rate_limited(data.matricule):
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives d'activation. Réessayez dans 15 minutes.",
        )

    # Generic message on EVERY mismatch — never reveal which field failed or
    # whether the matricule/police pair exists (enumeration defense).
    _generic_401 = HTTPException(status_code=401, detail="Informations non reconnues.")

    # ── Identity check against the ERP ──
    from backend.services import iway_soap_client as soap
    try:
        raw = await soap._call(
            "contrat", "getContratAdherentByMatricule",
            _retries=1,  # a wrong-creds fault must not hit the ERP 3× nor churn the circuit
            matricule=data.matricule, numPolice=data.num_police,
        )
    except Exception as e:
        # A SOAP fault = the ERP rejected the matricule/police (record not found /
        # invalid police) → treat as not recognized, NOT as an outage.
        if soap.is_data_fault(e):
            logger.info(f"Activation identity not recognized for {data.matricule}: {e}")
            raise _generic_401
        logger.warning(f"⚠️ Activation ERP check unavailable for {data.matricule}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Le service I-Way est temporairement indisponible — réessayez plus tard.",
        )

    identity = soap._map_identity(raw) if raw is not None else None
    if not identity or not (identity.get("date_naissance") or identity.get("cin")):
        raise _generic_401

    dob_ok = bool(
        data.date_naissance
        and _norm_date(data.date_naissance)
        and _norm_date(data.date_naissance) == _norm_date(identity.get("date_naissance"))
    )
    cin_ok = bool(
        data.cin
        and identity.get("cin")
        and data.cin.strip() == str(identity["cin"]).strip()
    )
    if not (dob_ok or cin_ok):
        raise _generic_401

    # ── Create the local account ──
    nom = identity.get("nom") or (identity.get("nom_complet") or "").strip() or data.matricule
    prenom = identity.get("prenom") or ""
    password_hash = bcrypt.hashpw(data.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import upsert_activated_user
        async with async_session_factory() as db:
            await upsert_activated_user(
                db, matricule=data.matricule, nom=nom, prenom=prenom,
                role="Adherent", password_hash=password_hash,
                num_police=data.num_police,
            )
            await db.commit()
    except Exception as e:
        logger.error(f"❌ Activation persistence failed for {data.matricule}: {e}")
        raise HTTPException(status_code=503, detail="Activation impossible pour le moment — réessayez plus tard.")

    token = create_jwt(data.matricule, role="Adherent", num_police=data.num_police)
    logger.info(f"✅ ERP account activated: {data.matricule} (Adherent)")
    return _login_response(token, {
        "matricule": data.matricule, "nom": nom, "prenom": prenom,
        "role": "Adherent", "email": "", "specialite": "",
    })


@router.post("/activate-ps")
async def activate_prestataire(data: ActivatePsInput):
    """First-login activation (prestataire) — REAL MODE ONLY.

    matricule fiscal → idTiers → contrat PS; the registered raison sociale must
    match the caller's claim. NOTE: weaker verification than the adhérent flow
    (no DOB/CIN equivalent) — acceptable for the pilot, flagged for an
    admin-approval queue later.
    """
    if not settings.IWAY_USE_REAL_API:
        raise HTTPException(
            status_code=400,
            detail="Activation indisponible en mode démo — utilisez un compte de démonstration.",
        )
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères.")
    if _activation_rate_limited(data.matricule_fiscal):
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives d'activation. Réessayez dans 15 minutes.",
        )

    _generic_401 = HTTPException(status_code=401, detail="Informations non reconnues.")
    from backend.services import iway_soap_client as soap
    try:
        resolved = await soap.get_contrat_ps_by_matricule_fiscal(data.matricule_fiscal)
        contrat_ps = (
            await soap.get_contrat_ps_by_id_tiers(resolved["id_tiers"])
            if resolved and resolved.get("id_tiers") else None
        )
    except Exception as e:
        # A SOAP fault = matricule fiscal / idTiers not found → not recognized, not an outage.
        if soap.is_data_fault(e):
            logger.info(f"PS activation identity not recognized for {data.matricule_fiscal}: {e}")
            raise _generic_401
        logger.warning(f"⚠️ PS activation ERP check unavailable for {data.matricule_fiscal}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Le service I-Way est temporairement indisponible — réessayez plus tard.",
        )

    if not resolved or not contrat_ps or not contrat_ps.get("raison_sociale"):
        raise _generic_401
    # Tolerant name match: the registered raison sociale must contain the
    # claimed name (accent/case-insensitive), or vice versa.
    from backend.services.iway_soap_client import _fold
    claimed, registered = _fold(data.nom_verification), _fold(contrat_ps["raison_sociale"])
    if not claimed or (claimed not in registered and registered not in claimed):
        raise _generic_401

    password_hash = bcrypt.hashpw(data.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        from backend.database.connection import async_session_factory
        from backend.database.repositories import upsert_activated_user
        async with async_session_factory() as db:
            await upsert_activated_user(
                db, matricule=data.matricule_fiscal,
                nom=contrat_ps["raison_sociale"], prenom="",
                role="Prestataire", password_hash=password_hash,
                id_tiers=resolved["id_tiers"],
            )
            await db.commit()
    except Exception as e:
        logger.error(f"❌ PS activation persistence failed for {data.matricule_fiscal}: {e}")
        raise HTTPException(status_code=503, detail="Activation impossible pour le moment — réessayez plus tard.")

    token = create_jwt(data.matricule_fiscal, role="Prestataire", id_tiers=resolved["id_tiers"])
    logger.info(f"✅ ERP account activated: {data.matricule_fiscal} (Prestataire, idTiers={resolved['id_tiers']})")
    return _login_response(token, {
        "matricule": data.matricule_fiscal, "nom": contrat_ps["raison_sociale"],
        "prenom": "", "role": "Prestataire", "email": "", "specialite": "",
    })


@router.post("/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Sliding-session renewal: exchange a valid (non-expired) token for a fresh one.

    Claims (role / num_police / id_tiers) are carried over from the verified
    old token so renewal never downgrades an ERP user to defaults.
    """
    payload = verify_jwt(credentials.credentials)
    token = create_jwt(
        payload.get("sub", ""),
        role=payload.get("role"),
        num_police=payload.get("num_police", ""),
        id_tiers=payload.get("id_tiers", ""),
    )
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
