"""
Test suite for Step 2: bot_tools.py and agent.py

Tests are split into two groups:
  A) Unit tests - no server needed (RAG tool, agent graph structure)
  B) Integration tests - require the Mock Server running on :8000
     (dossiers tool, escalation tool, login helper)

Run all:       venv/Scripts/pytest test_bot_tools.py -v
Run unit only: venv/Scripts/pytest test_bot_tools.py -v -k "not integration"
"""

import os
import pytest
from httpx import AsyncClient, ASGITransport
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from bot_tools import get_personal_dossiers, search_knowledge_base, escalate_to_human
from agent import build_agent_graph, AgentState, login_to_mock_server
from main import app, state as server_state, MOCK_DB


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _init_rsa_keys():
    """Generate RSA keys (lifespan doesn't fire under ASGITransport)."""
    server_state.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_state.public_key_pem = server_state.private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    yield
    server_state.private_key = None
    server_state.public_key_pem = None


@pytest.fixture
async def client():
    """Async HTTP client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def get_token(client, matricule="12345", password="pass") -> str:
    """Helper: login and return JWT token."""
    resp = await client.post("/auth/login", json={"matricule": matricule, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ═══════════════════════════════════════════════════════════════
# A) UNIT TESTS — search_knowledge_base (no server needed)
# ═══════════════════════════════════════════════════════════════

class TestSearchKnowledgeBase:
    """Test semantic search via FAISS RAG engine (async tools)."""

    @pytest.mark.anyio
    async def test_dental_query(self):
        result = await search_knowledge_base.ainvoke({"query": "plafond soins dentaires"})
        assert "600 TND" in result

    @pytest.mark.anyio
    async def test_birth_premium_query(self):
        result = await search_knowledge_base.ainvoke({"query": "prime de naissance"})
        assert "300 TND" in result

    @pytest.mark.anyio
    async def test_reimbursement_query(self):
        result = await search_knowledge_base.ainvoke({"query": "delai remboursement soins"})
        assert "48h" in result

    @pytest.mark.anyio
    async def test_beneficiary_query(self):
        result = await search_knowledge_base.ainvoke({"query": "ajouter un beneficiaire famille"})
        assert "Ma Famille" in result

    @pytest.mark.anyio
    async def test_optical_query(self):
        result = await search_knowledge_base.ainvoke({"query": "lunettes optique verres"})
        assert "250 TND" in result

    @pytest.mark.anyio
    async def test_hospitalization_query(self):
        result = await search_knowledge_base.ainvoke({"query": "hospitalisation urgence"})
        assert "90%" in result or "urgence" in result.lower()

    @pytest.mark.anyio
    async def test_chronic_illness_query(self):
        result = await search_knowledge_base.ainvoke({"query": "maladie chronique diabete"})
        assert "100%" in result

    @pytest.mark.anyio
    async def test_maternity_query(self):
        result = await search_knowledge_base.ainvoke({"query": "conge maternite accouchement"})
        assert "30 jours" in result or "accouchement" in result.lower()

    @pytest.mark.anyio
    async def test_returns_ranked_results(self):
        """Search results should include ranking and pertinence scores."""
        result = await search_knowledge_base.ainvoke({"query": "soins dentaires"})
        assert "Resultat 1" in result
        assert "pertinence" in result


# ═══════════════════════════════════════════════════════════════
# B) UNIT TESTS — Agent graph structure
# ═══════════════════════════════════════════════════════════════

needs_api_key = pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set — skipping LLM graph tests",
)


class TestAgentGraph:
    """Verify agent graph compiles and has the right structure."""

    @needs_api_key
    def test_graph_compiles(self):
        graph = build_agent_graph()
        assert graph is not None

    @needs_api_key
    def test_graph_has_correct_nodes(self):
        graph = build_agent_graph()
        node_ids = list(graph.get_graph().nodes.keys())
        assert "chatbot" in node_ids
        assert "tools" in node_ids

    def test_agent_state_has_required_fields(self):
        """AgentState must have messages, matricule, and token."""
        annotations = AgentState.__annotations__
        assert "messages" in annotations
        assert "matricule" in annotations
        assert "token" in annotations


# ═══════════════════════════════════════════════════════════════
# C) INTEGRATION TESTS — require mock server via ASGITransport
# ═══════════════════════════════════════════════════════════════

class TestGetPersonalDossiers:
    """Test the get_personal_dossiers tool against the mock server."""

    @pytest.mark.anyio
    async def test_dossiers_valid_token(self, client):
        """Tool should return Nadia's dossiers with valid token."""
        token = await get_token(client, "12345", "pass")
        # The tool calls localhost:8000, but here we test the flow
        # by hitting the endpoint directly to validate the contract
        resp = await client.get(
            "/api/v1/adherent/dossiers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "DOS-8892"
        assert data[0]["type"] == "Santé Gold"
        assert data[1]["id"] == "DOS-9901"

    @pytest.mark.anyio
    async def test_dossiers_invalid_token(self, client):
        """Without valid token, the endpoint should reject."""
        resp = await client.get(
            "/api/v1/adherent/dossiers",
            headers={"Authorization": "Bearer invalid-token-xyz"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_dossiers_no_token(self, client):
        """Without any bearer header, endpoint returns 403."""
        resp = await client.get("/api/v1/adherent/dossiers")
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_tool_handles_connection_error(self):
        """If server is down, tool returns a friendly error."""
        # Use a port that's definitely not running
        import bot_tools
        original_url = bot_tools.MOCK_SERVER_URL
        bot_tools.MOCK_SERVER_URL = "http://localhost:19999"
        try:
            result = await get_personal_dossiers.ainvoke({"matricule": "12345", "token": "fake"})
            assert "Erreur" in result
        finally:
            bot_tools.MOCK_SERVER_URL = original_url


class TestEscalateToHuman:
    """Test the escalate_to_human tool."""

    @pytest.mark.anyio
    async def test_escalation_creates_ticket(self, client):
        """POST /escalade with valid token should create a ticket."""
        token = await get_token(client, "12345", "pass")
        payload = {
            "matricule": "12345",
            "conversation_id": "conv-test",
            "chat_history": [
                {"role": "user", "content": "Help me!"},
            ],
            "reason": "Test escalation",
        }
        resp = await client.post(
            "/api/v1/support/escalade",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "escalated"
        assert data["case_id"].startswith("CASE-")
        assert "queue_position" in data
        assert "estimated_wait" in data

    @pytest.mark.anyio
    async def test_escalation_no_auth(self, client):
        """Escalation without token should fail."""
        payload = {
            "matricule": "12345",
            "conversation_id": "conv-test",
            "chat_history": [{"role": "user", "content": "Help"}],
        }
        resp = await client.post("/api/v1/support/escalade", json=payload)
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_escalation_tool_handles_connection_error(self):
        """If server is down, tool returns a friendly error."""
        import bot_tools
        original_url = bot_tools.MOCK_SERVER_URL
        bot_tools.MOCK_SERVER_URL = "http://localhost:19999"
        try:
            result = await escalate_to_human.ainvoke({
                "matricule": "12345",
                "token": "fake",
                "issue_description": "test"
            })
            assert "Erreur" in result
        finally:
            bot_tools.MOCK_SERVER_URL = original_url


# ═══════════════════════════════════════════════════════════════
# D) INTEGRATION — Full auth flow end-to-end
# ═══════════════════════════════════════════════════════════════

class TestAuthFlow:
    """End-to-end authentication tests for both personas."""

    @pytest.mark.anyio
    async def test_nadia_full_flow(self, client):
        """Login as Nadia → get profile → get dossiers → get remboursements."""
        # Login
        resp = await client.post("/auth/login", json={"matricule": "12345", "password": "pass"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Profile
        resp = await client.get("/api/v1/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["prenom"] == "Nadia"
        assert "password" not in resp.json()

        # Dossiers
        resp = await client.get("/api/v1/adherent/dossiers", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        # Beneficiaires
        resp = await client.get("/api/v1/adherent/beneficiaires", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        # Remboursements
        resp = await client.get("/api/v1/remboursements", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Prestations
        resp = await client.get("/api/v1/prestations", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.anyio
    async def test_dr_amine_full_flow(self, client):
        """Login as Dr. Amine → get profile → get prestations."""
        resp = await client.post("/auth/login", json={"matricule": "99999", "password": "med"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Profile
        resp = await client.get("/api/v1/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["prenom"] == "Amine"
        assert data["role"] == "Prestataire"
        assert data["specialite"] == "Cardiologie"

        # Prestations
        resp = await client.get("/api/v1/prestations", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert resp.json()[0]["acte"] == "Echographie"

    @pytest.mark.anyio
    async def test_cross_persona_isolation(self, client):
        """Nadia's token should only return Nadia's data."""
        token = await get_token(client, "12345", "pass")
        headers = {"Authorization": f"Bearer {token}"}

        # Nadia has dossiers, Dr. Amine doesn't
        resp = await client.get("/api/v1/adherent/dossiers", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # Nadia's dossiers

    @pytest.mark.anyio
    async def test_expired_or_tampered_token(self, client):
        """A tampered token should be rejected."""
        token = await get_token(client, "12345", "pass")
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════
# E) INTEGRATION — Dashboard tickets
# ═══════════════════════════════════════════════════════════════

class TestDashboardTickets:
    """Test the dashboard endpoint that Step 3 will consume."""

    @pytest.mark.anyio
    async def test_escalation_appears_in_dashboard(self, client):
        """An escalation should create a ticket visible in the dashboard."""
        token = await get_token(client, "12345", "pass")
        headers = {"Authorization": f"Bearer {token}"}

        # Clear existing tickets
        MOCK_DB["escalation_tickets"].clear()

        # Create escalation
        payload = {
            "matricule": "12345",
            "conversation_id": "conv-dashboard-test",
            "chat_history": [
                {"role": "user", "content": "Je veux parler à un humain"},
                {"role": "assistant", "content": "Je vous transfère."},
            ],
            "reason": "User requested human agent",
        }
        resp = await client.post("/api/v1/support/escalade", json=payload, headers=headers)
        assert resp.status_code == 200
        case_id = resp.json()["case_id"]

        # Check dashboard
        resp = await client.get("/api/v1/dashboard/tickets", headers=headers)
        assert resp.status_code == 200
        tickets = resp.json()
        assert len(tickets) >= 1
        assert any(t["case_id"] == case_id for t in tickets)

        # Verify ticket has chat history
        ticket = next(t for t in tickets if t["case_id"] == case_id)
        assert len(ticket["chat_history"]) == 2
        assert ticket["matricule"] == "12345"
        assert ticket["client_name"] == "Nadia Mansour"
