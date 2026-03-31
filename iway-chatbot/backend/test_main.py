"""
Test suite for the I-Way Digital Twin API (with RS256 JWT Auth).
Run with:  .\venv\Scripts\pytest.exe test_main.py -v
"""
import pytest
from httpx import AsyncClient, ASGITransport
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from main import app, MOCK_DB, state


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _init_rsa_keys():
    """Generate RSA keys before each test (lifespan doesn't fire under ASGITransport)."""
    state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state.public_key_pem = state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    yield
    state.private_key = None
    state.public_key_pem = None


@pytest.fixture
async def client():
    """Async HTTP client wired directly to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def login_as(client, matricule: str, password: str) -> str:
    """Helper: logs in and returns the Bearer token."""
    resp = await client.post("/auth/login", json={"matricule": matricule, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    """Helper: returns Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ── 1. System / Root ─────────────────────────────────────────

@pytest.mark.anyio
async def test_root_returns_status(client):
    """GET / should return system info and status (public)."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "personas_available" in data
    assert data["docs"] == "/docs"


# ── 2. Auth – Login ──────────────────────────────────────────

@pytest.mark.anyio
async def test_login_nadia(client):
    """POST /auth/login with Nadia's credentials returns a JWT."""
    resp = await client.post("/auth/login", json={"matricule": "12345", "password": "pass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["matricule"] == "12345"
    assert data["user"]["role"] == "Adherent"


@pytest.mark.anyio
async def test_login_dr_amine(client):
    """POST /auth/login with Dr. Amine's credentials returns a JWT."""
    resp = await client.post("/auth/login", json={"matricule": "99999", "password": "med"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["matricule"] == "99999"
    assert data["user"]["role"] == "Prestataire"


@pytest.mark.anyio
async def test_login_wrong_password(client):
    """Wrong password should return 401."""
    resp = await client.post("/auth/login", json={"matricule": "12345", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_login_unknown_user(client):
    """Unknown matricule should return 401."""
    resp = await client.post("/auth/login", json={"matricule": "00000", "password": "x"})
    assert resp.status_code == 401


# ── 3. Auth – Public Key ─────────────────────────────────────

@pytest.mark.anyio
async def test_public_key(client):
    """GET /auth/public-key should return the RSA public key PEM."""
    resp = await client.get("/auth/public-key")
    assert resp.status_code == 200
    data = resp.json()
    assert data["algorithm"] == "RS256"
    assert "BEGIN PUBLIC KEY" in data["public_key"]


# ── 4. Protected – /api/v1/me ────────────────────────────────

@pytest.mark.anyio
async def test_me_requires_auth(client):
    """GET /api/v1/me without token should return 403."""
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_me_nadia(client):
    """GET /api/v1/me with Nadia's token returns her profile (no password)."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/me", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["matricule"] == "12345"
    assert data["role"] == "Adherent"
    assert "password" not in data


@pytest.mark.anyio
async def test_me_dr_amine(client):
    """GET /api/v1/me with Dr. Amine's token returns his profile."""
    token = await login_as(client, "99999", "med")
    resp = await client.get("/api/v1/me", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["matricule"] == "99999"
    assert data["specialite"] == "Cardiologie"


# ── 5. Knowledge Base (Public) ───────────────────────────────

@pytest.mark.anyio
async def test_knowledge_base_returns_items(client):
    """GET /api/v1/knowledge-base should return all KB entries (public)."""
    resp = await client.get("/api/v1/knowledge-base")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == len(MOCK_DB["knowledge_base"])
    assert len(data["items"]) >= 3


# ── 6. Adherent – Dossiers (Protected) ──────────────────────

@pytest.mark.anyio
async def test_dossiers_nadia(client):
    """Nadia has 2 dossiers."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/adherent/dossiers", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "DOS-8892"


@pytest.mark.anyio
async def test_dossiers_no_auth_returns_403(client):
    """Dossiers without token should be rejected."""
    resp = await client.get("/api/v1/adherent/dossiers")
    assert resp.status_code == 403


# ── 7. Adherent – Bénéficiaires (Protected) ──────────────────

@pytest.mark.anyio
async def test_beneficiaires_nadia(client):
    """Nadia has 2 beneficiaries."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/adherent/beneficiaires", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    liens = {b["lien"] for b in data}
    assert "Enfant" in liens
    assert "Conjoint" in liens


# ── 8. Prestations (Protected) ──────────────────────────────

@pytest.mark.anyio
async def test_prestations_nadia(client):
    """Nadia should have at least 1 prestation."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/prestations", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["acte"] == "Consultation Généraliste"


@pytest.mark.anyio
async def test_prestations_dr_amine(client):
    """Dr. Amine (Prestataire) should also have prestations."""
    token = await login_as(client, "99999", "med")
    resp = await client.get("/api/v1/prestations", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["acte"] == "Echographie"


# ── 9. Remboursements (Protected) ───────────────────────────

@pytest.mark.anyio
async def test_remboursements_nadia(client):
    """Nadia has at least 1 remboursement."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/remboursements", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["status"] == "Payé"


@pytest.mark.anyio
async def test_remboursements_dr_amine_empty(client):
    """Dr. Amine has no remboursements."""
    token = await login_as(client, "99999", "med")
    resp = await client.get("/api/v1/remboursements", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json() == []


# ── 10. Réclamations (Protected) ─────────────────────────────

@pytest.mark.anyio
async def test_reclamations_history(client):
    """Nadia has an existing closed ticket."""
    token = await login_as(client, "12345", "pass")
    resp = await client.get("/api/v1/reclamations", headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["statut"] == "Clôturé" for t in data)


@pytest.mark.anyio
async def test_create_reclamation(client):
    """POST /api/v1/reclamations should create a new ticket."""
    token = await login_as(client, "12345", "pass")
    payload = {
        "matricule": "12345",
        "objet": "Test réclamation",
        "message": "Ceci est un message de test pour vérifier la création d'un ticket."
    }
    resp = await client.post("/api/v1/reclamations", json=payload, headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    ticket = data["ticket"]
    assert ticket["statut"] == "Ouvert"
    assert ticket["id"].startswith("TICKET-")


@pytest.mark.anyio
async def test_create_reclamation_missing_fields(client):
    """Omitting required fields should return a 422 validation error."""
    token = await login_as(client, "12345", "pass")
    resp = await client.post("/api/v1/reclamations", json={"matricule": "12345"}, headers=auth_header(token))
    assert resp.status_code == 422


# ── 11. Escalade (Protected) ─────────────────────────────────

@pytest.mark.anyio
async def test_escalade(client):
    """POST /api/v1/support/escalade should return escalation info."""
    token = await login_as(client, "12345", "pass")
    payload = {
        "matricule": "12345",
        "conversation_id": "conv-abc-123",
        "chat_history": [
            {"role": "user", "content": "J'ai un problème urgent"},
            {"role": "assistant", "content": "Je transfère vers un agent."}
        ],
        "reason": "Problème critique"
    }
    resp = await client.post("/api/v1/support/escalade", json=payload, headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "escalated"
    assert data["case_id"].startswith("CASE-")
    assert "queue_position" in data
    assert "estimated_wait" in data


@pytest.mark.anyio
async def test_escalade_missing_history(client):
    """chat_history is required – omitting it should 422."""
    token = await login_as(client, "12345", "pass")
    payload = {
        "matricule": "12345",
        "conversation_id": "conv-xyz"
    }
    resp = await client.post("/api/v1/support/escalade", json=payload, headers=auth_header(token))
    assert resp.status_code == 422
