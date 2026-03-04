"""
Test suite for the I-Way Digital Twin API.
Run with:  .\venv\Scripts\pytest.exe test_main.py -v
"""
import pytest
from httpx import AsyncClient, ASGITransport
from main import app, MOCK_DB


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP client wired directly to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── 1. System / Root ─────────────────────────────────────────

@pytest.mark.anyio
async def test_root_returns_status(client):
    """GET / should return system info and status."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "personas_available" in data
    assert data["docs"] == "/docs"


# ── 2. Auth – GET /api/v1/me ──────────────────────────────────

@pytest.mark.anyio
async def test_me_default_persona(client):
    """Without X-User-Id header, defaults to NADIA_2024."""
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["matricule"] == "NADIA_2024"
    assert data["role"] == "Adherent"


@pytest.mark.anyio
async def test_me_with_valid_header(client):
    """X-User-Id: DOC_AMINE should return the Prestataire profile."""
    resp = await client.get("/api/v1/me", headers={"X-User-Id": "DOC_AMINE"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["matricule"] == "DOC_AMINE"
    assert data["role"] == "Prestataire"
    assert data["specialite"] == "Cardiologie"


@pytest.mark.anyio
async def test_me_unknown_user_returns_403(client):
    """An unknown X-User-Id must be rejected with 403."""
    resp = await client.get("/api/v1/me", headers={"X-User-Id": "UNKNOWN"})
    assert resp.status_code == 403


# ── 3. Knowledge Base ────────────────────────────────────────

@pytest.mark.anyio
async def test_knowledge_base_returns_items(client):
    """GET /api/v1/knowledge-base should return all KB entries."""
    resp = await client.get("/api/v1/knowledge-base")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == len(MOCK_DB["knowledge_base"])
    assert len(data["items"]) >= 3


# ── 4. Adherent – Dossiers ───────────────────────────────────

@pytest.mark.anyio
async def test_dossiers_existing_user(client):
    """NADIA_2024 has 2 dossiers."""
    resp = await client.get("/api/v1/adherent/dossiers", params={"matricule": "NADIA_2024"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "DOS-8892"


@pytest.mark.anyio
async def test_dossiers_unknown_user_returns_empty(client):
    """An unknown matricule should return an empty list, not 404."""
    resp = await client.get("/api/v1/adherent/dossiers", params={"matricule": "NOBODY"})
    assert resp.status_code == 200
    assert resp.json() == []


# ── 5. Adherent – Bénéficiaires ──────────────────────────────

@pytest.mark.anyio
async def test_beneficiaires_existing_user(client):
    """NADIA_2024 has 2 beneficiaries."""
    resp = await client.get("/api/v1/adherent/beneficiaires", params={"matricule": "NADIA_2024"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    liens = {b["lien"] for b in data}
    assert "Enfant" in liens
    assert "Conjoint" in liens


@pytest.mark.anyio
async def test_beneficiaires_unknown_user(client):
    resp = await client.get("/api/v1/adherent/beneficiaires", params={"matricule": "NOBODY"})
    assert resp.status_code == 200
    assert resp.json() == []


# ── 6. Prestations ───────────────────────────────────────────

@pytest.mark.anyio
async def test_prestations_adherent(client):
    """NADIA_2024 should have at least 1 prestation."""
    resp = await client.get("/api/v1/prestations", params={"matricule": "NADIA_2024"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["acte"] == "Consultation Généraliste"


@pytest.mark.anyio
async def test_prestations_prestataire(client):
    """DOC_AMINE (Prestataire) should also have prestations."""
    resp = await client.get("/api/v1/prestations", params={"matricule": "DOC_AMINE"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["acte"] == "Echographie"


# ── 7. Remboursements ────────────────────────────────────────

@pytest.mark.anyio
async def test_remboursements(client):
    """NADIA_2024 has at least 1 remboursement."""
    resp = await client.get("/api/v1/remboursements", params={"matricule": "NADIA_2024"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["status"] == "Payé"


@pytest.mark.anyio
async def test_remboursements_empty(client):
    resp = await client.get("/api/v1/remboursements", params={"matricule": "DOC_AMINE"})
    assert resp.status_code == 200
    assert resp.json() == []


# ── 8. Réclamations – GET ────────────────────────────────────

@pytest.mark.anyio
async def test_reclamations_history(client):
    """NADIA_2024 has an existing closed ticket."""
    resp = await client.get("/api/v1/reclamations", params={"matricule": "NADIA_2024"})
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["statut"] == "Clôturé" for t in data)


# ── 9. Réclamations – POST (create) ──────────────────────────

@pytest.mark.anyio
async def test_create_reclamation(client):
    """POST /api/v1/reclamations should create a new ticket."""
    payload = {
        "matricule": "NADIA_2024",
        "objet": "Test réclamation",
        "message": "Ceci est un message de test pour vérifier la création d'un ticket."
    }
    resp = await client.post("/api/v1/reclamations", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    ticket = data["ticket"]
    assert ticket["statut"] == "Ouvert"
    assert ticket["id"].startswith("TICKET-")


@pytest.mark.anyio
async def test_create_reclamation_new_user(client):
    """Creating a réclamation for a new matricule should auto-initialise."""
    payload = {
        "matricule": "NEW_USER_99",
        "objet": "Premier contact",
        "message": "Bonjour, j'ai un problème."
    }
    resp = await client.post("/api/v1/reclamations", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.anyio
async def test_create_reclamation_missing_fields(client):
    """Omitting required fields should return a 422 validation error."""
    resp = await client.post("/api/v1/reclamations", json={"matricule": "NADIA_2024"})
    assert resp.status_code == 422


# ── 10. Escalade ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_escalade(client):
    """POST /api/v1/support/escalade should return escalation info."""
    payload = {
        "matricule": "NADIA_2024",
        "conversation_id": "conv-abc-123",
        "chat_history": [
            {"role": "user", "content": "J'ai un problème urgent"},
            {"role": "assistant", "content": "Je transfère vers un agent."}
        ],
        "reason": "Problème critique"
    }
    resp = await client.post("/api/v1/support/escalade", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "escalated"
    assert data["case_id"].startswith("CASE-")
    assert "queue_position" in data
    assert "estimated_wait" in data


@pytest.mark.anyio
async def test_escalade_missing_history(client):
    """chat_history is required – omitting it should 422."""
    payload = {
        "matricule": "NADIA_2024",
        "conversation_id": "conv-xyz"
    }
    resp = await client.post("/api/v1/support/escalade", json=payload)
    assert resp.status_code == 422
