"""
Offline tests for the activation + password auth flow (routers/auth.py).

The ERP exposes no login operation, so real auth = identity verification
(getContratAdherentByMatricule → DOB/CIN match) at activation + a local bcrypt
password afterwards. Everything here runs WITHOUT the LAN or Postgres: the
SOAP layer and the DB session factory are stubbed.

Run:  GOOGLE_API_KEY=offline pytest tests/test_auth_activation.py -v
"""

import os
import asyncio
from contextlib import asynccontextmanager

os.environ.setdefault("GOOGLE_API_KEY", "offline")

import bcrypt
import pytest
from fastapi import HTTPException

from backend.routers import auth
from backend.services import iway_soap_client as soap


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _rsa_keys(tmp_path_factory):
    """The endpoints sign/verify JWTs — generate a throwaway keypair."""
    auth.init_keys(str(tmp_path_factory.mktemp("jwt_keys")))


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    auth._ACTIVATION_ATTEMPTS.clear()
    yield
    auth._ACTIVATION_ATTEMPTS.clear()


class _FakeDB:
    async def commit(self):
        pass


def _stub_db(monkeypatch, captured: dict):
    """Replace the session factory + repo functions (no Postgres needed)."""
    from backend.database import connection, repositories

    @asynccontextmanager
    async def _factory():
        yield _FakeDB()

    async def _upsert(db, **kw):
        captured.update(kw)

    async def _touch(db, matricule):
        captured["last_login_touched"] = matricule

    monkeypatch.setattr(connection, "async_session_factory", _factory)
    monkeypatch.setattr(repositories, "upsert_activated_user", _upsert)
    monkeypatch.setattr(repositories, "touch_last_login", _touch)


def _stub_erp_identity(monkeypatch, *, dob="1985-06-12", cin="09876543"):
    """getContratAdherentByMatricule returns a fixed identity DTO."""
    async def _call_stub(service, op, **k):
        assert (service, op) == ("contrat", "getContratAdherentByMatricule")
        return {
            "numContrat": "C-1",
            "personnePhysique": {
                "nom": "Mansour", "prenom": "Nadia", "nomComplet": "Nadia Mansour",
                "dateNaissance": dob, "numeroPieceId": cin,
                "numeroPolice": "12012500000011",
            },
        }
    monkeypatch.setattr(soap, "_call", _call_stub)


def _activate(**kw):
    body = {"matricule": "10012", "num_police": "12012500000011",
            "date_naissance": "1985-06-12", "new_password": "motdepasse8", **kw}
    return asyncio.run(auth.activate_account(auth.ActivateInput(**body)))


# ──────────────────────────────────────────────────────────────
# /auth/activate
# ──────────────────────────────────────────────────────────────

def test_activation_refused_in_mock_mode(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", False, raising=False)
    with pytest.raises(HTTPException) as e:
        _activate()
    assert e.value.status_code == 400
    assert "démo" in e.value.detail


def test_activation_dob_match_issues_jwt_with_num_police(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_erp_identity(monkeypatch)
    captured = {}
    _stub_db(monkeypatch, captured)

    out = _activate()

    assert out["user"]["role"] == "Adherent"
    assert out["user"]["nom"] == "Mansour"
    payload = auth.verify_jwt(out["access_token"])
    assert payload["sub"] == "10012"
    assert payload["num_police"] == "12012500000011"
    assert payload["role"] == "Adherent"
    # Stored hash verifies the chosen password; source flow marks ERP
    assert bcrypt.checkpw(b"motdepasse8", captured["password_hash"].encode())
    assert captured["num_police"] == "12012500000011"


def test_activation_cin_match_when_no_dob(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_erp_identity(monkeypatch)
    _stub_db(monkeypatch, {})

    out = _activate(date_naissance=None, cin="09876543")
    assert auth.verify_jwt(out["access_token"])["sub"] == "10012"


def test_activation_wrong_dob_is_generic_401(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_erp_identity(monkeypatch)

    with pytest.raises(HTTPException) as e:
        _activate(date_naissance="1990-01-01")
    assert e.value.status_code == 401
    # Enumeration defense: generic message, no hint about which field failed
    assert e.value.detail == "Informations non reconnues."


def test_activation_requires_dob_or_cin(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    with pytest.raises(HTTPException) as e:
        _activate(date_naissance=None, cin=None)
    assert e.value.status_code == 400


def test_activation_rejects_short_password(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    with pytest.raises(HTTPException) as e:
        _activate(new_password="court")
    assert e.value.status_code == 400


def test_activation_transport_error_is_503(monkeypatch):
    """ERP unreachable (transport/connection error) → 503, not 401."""
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _boom(*a, **k):
        raise ConnectionError("server unreachable (off-LAN)")

    monkeypatch.setattr(soap, "_call", _boom)
    with pytest.raises(HTTPException) as e:
        _activate()
    assert e.value.status_code == 503


def test_activation_soap_fault_is_generic_401(monkeypatch):
    """A SOAP Fault (wrong matricule/police → record-not-found / invalid police)
    is the ERP REJECTING the identity — must surface as the generic 401, never a
    misleading 503 'service indisponible'."""
    from zeep.exceptions import Fault
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)

    async def _fault(*a, **k):
        raise Fault("DataNotFoundException: police invalide")

    monkeypatch.setattr(soap, "_call", _fault)
    with pytest.raises(HTTPException) as e:
        _activate(num_police="0000000000000")
    assert e.value.status_code == 401
    assert e.value.detail == "Informations non reconnues."


def test_activation_rate_limited_after_5_attempts(monkeypatch):
    monkeypatch.setattr(auth.settings, "IWAY_USE_REAL_API", True, raising=False)
    _stub_erp_identity(monkeypatch)

    for _ in range(5):
        with pytest.raises(HTTPException) as e:
            _activate(date_naissance="1990-01-01")   # wrong DOB each time
        assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        _activate(date_naissance="1990-01-01")
    assert e.value.status_code == 429                 # DOB brute-force stopped


# ──────────────────────────────────────────────────────────────
# /auth/login — demo personas unchanged + ERP-user fallback
# ──────────────────────────────────────────────────────────────

def test_mock_persona_login_unchanged():
    out = asyncio.run(auth.login(auth.LoginInput(matricule="12345", password="pass")))
    assert out["user"]["nom"] == "Mansour"
    payload = auth.verify_jwt(out["access_token"])
    assert payload["role"] == "Adherent"
    assert payload["num_police"] == ""                # demo personas carry no police


def test_login_falls_back_to_activated_erp_user(monkeypatch):
    pwd_hash = bcrypt.hashpw(b"secret-erp-1", bcrypt.gensalt()).decode()

    async def _resolve(matricule):
        assert matricule == "10012"
        return {
            "matricule": "10012", "nom": "Mansour", "prenom": "Nadia",
            "role": "Adherent", "email": "", "specialite": "",
            "password_hash": pwd_hash, "num_police": "12012500000011",
            "id_tiers": "", "source": "erp",
        }

    monkeypatch.setattr(auth, "resolve_user", _resolve)
    captured = {}
    _stub_db(monkeypatch, captured)

    out = asyncio.run(auth.login(auth.LoginInput(matricule="10012", password="secret-erp-1")))
    payload = auth.verify_jwt(out["access_token"])
    assert payload["num_police"] == "12012500000011"
    assert captured.get("last_login_touched") == "10012"

    with pytest.raises(HTTPException):
        asyncio.run(auth.login(auth.LoginInput(matricule="10012", password="wrong")))


# ──────────────────────────────────────────────────────────────
# /auth/refresh — claims preserved
# ──────────────────────────────────────────────────────────────

def test_refresh_preserves_erp_claims():
    class _Creds:
        credentials = auth.create_jwt("10012", role="Adherent",
                                      num_police="12012500000011")

    out = asyncio.run(auth.refresh_token(_Creds()))
    payload = auth.verify_jwt(out["access_token"])
    assert payload["sub"] == "10012"
    assert payload["num_police"] == "12012500000011"
    assert payload["role"] == "Adherent"
