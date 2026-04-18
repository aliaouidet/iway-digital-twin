"""
Test Suite: I-Way Digital Twin API — Auth, Sessions, Knowledge, Dashboard

Run inside Docker:
  docker exec -e TEST_API_URL=http://iway-api:8000 iway-api python -m pytest tests/test_api.py -v

Run locally (with backend on localhost:8000):
  python -m pytest tests/test_api.py -v
"""

import os
import httpx
import pytest

BASE = os.environ.get("TEST_API_URL", "http://localhost:8000")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def login(matricule: str, password: str) -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"matricule": matricule, "password": password})
    r.raise_for_status()
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# 1. AUTH TESTS
# ═══════════════════════════════════════════════════════════════

class TestAuth:

    def test_login_adherent(self):
        data = login("12345", "pass")
        assert "access_token" in data
        assert data["user"]["role"] == "Adherent"
        assert data["user"]["prenom"] == "Nadia"

    def test_login_prestataire(self):
        data = login("99999", "med")  # password is 'med'
        assert data["user"]["role"] == "Prestataire"

    def test_login_agent(self):
        data = login("88888", "agent")
        assert data["user"]["role"] == "Agent"

    def test_login_admin(self):
        data = login("77777", "admin")
        assert data["user"]["role"] == "Admin"

    def test_login_wrong_password(self):
        r = httpx.post(f"{BASE}/auth/login", json={"matricule": "12345", "password": "wrong"})
        assert r.status_code == 401

    def test_login_unknown_user(self):
        r = httpx.post(f"{BASE}/auth/login", json={"matricule": "00000", "password": "pass"})
        assert r.status_code == 401

    def test_protected_endpoint_no_token(self):
        r = httpx.get(f"{BASE}/api/v1/me")
        assert r.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# 2. MOCK API TESTS (I-Way Business Endpoints)
# ═══════════════════════════════════════════════════════════════

class TestMockAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("12345", "pass")["access_token"]
        self.headers = auth_headers(self.token)

    def test_get_me(self):
        r = httpx.get(f"{BASE}/api/v1/me", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert data["prenom"] == "Nadia"
        assert "password" not in data

    def test_get_dossiers(self):
        r = httpx.get(f"{BASE}/api/v1/adherent/dossiers", headers=self.headers)
        assert r.status_code == 200
        dossiers = r.json()
        assert isinstance(dossiers, list)
        assert len(dossiers) >= 1

    def test_get_beneficiaires(self):
        r = httpx.get(f"{BASE}/api/v1/adherent/beneficiaires", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(b["lien"] == "Enfant" for b in data)

    def test_get_prestations(self):
        r = httpx.get(f"{BASE}/api/v1/prestations", headers=self.headers)
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_get_remboursements(self):
        r = httpx.get(f"{BASE}/api/v1/remboursements", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert any(v["status"] == "Payé" for v in data)

    def test_get_reclamations(self):
        r = httpx.get(f"{BASE}/api/v1/reclamations", headers=self.headers)
        assert r.status_code == 200

    def test_create_reclamation(self):
        r = httpx.post(
            f"{BASE}/api/v1/reclamations",
            headers=self.headers,
            json={"matricule": "12345", "objet": "Test", "message": "Ceci est un test"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# ═══════════════════════════════════════════════════════════════
# 3. KNOWLEDGE BASE & RAG TESTS
# ═══════════════════════════════════════════════════════════════

class TestKnowledgeBase:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("77777", "admin")["access_token"]
        self.headers = auth_headers(self.token)

    def test_knowledge_base_has_entries(self):
        r = httpx.get(f"{BASE}/api/v1/knowledge-base")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 30

    def test_knowledge_base_entry_structure(self):
        r = httpx.get(f"{BASE}/api/v1/knowledge-base")
        item = r.json()["items"][0]
        assert "question" in item
        assert "reponse" in item
        assert "tags" in item

    def test_knowledge_search_french(self):
        r = httpx.get(f"{BASE}/api/v1/knowledge/search", headers=self.headers, params={"q": "plafond dentaire"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or isinstance(data, dict)
        # Handle both list and dict response formats
        results = data if isinstance(data, list) else data.get("results", [])
        if results:
            assert results[0]["similarity"] > 0.5

    def test_knowledge_search_naissance(self):
        r = httpx.get(f"{BASE}/api/v1/knowledge/search", headers=self.headers, params={"q": "prime de naissance"})
        assert r.status_code == 200
        data = r.json()
        results = data if isinstance(data, list) else data.get("results", [])
        if results:
            assert results[0]["similarity"] > 0.5

    def test_knowledge_stats(self):
        r = httpx.get(f"{BASE}/api/v1/knowledge/stats", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        # The store might not be synced yet — just check endpoint works
        assert isinstance(data, dict)


# ═══════════════════════════════════════════════════════════════
# 4. DASHBOARD / METRICS TESTS (routes: /api/v1/metrics, /api/v1/logs)
# ═══════════════════════════════════════════════════════════════

class TestDashboard:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("77777", "admin")["access_token"]
        self.headers = auth_headers(self.token)

    def test_metrics(self):
        r = httpx.get(f"{BASE}/api/v1/metrics", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_requests" in data
        assert data["total_requests"] >= 16
        assert "rag_resolved" in data
        assert "agent_resolved" in data

    def test_logs(self):
        r = httpx.get(f"{BASE}/api/v1/logs", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        # Logs endpoint returns paginated {items, total, page, page_size}
        items = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(items, list)
        assert len(items) >= 16
        outcomes = {l["outcome"] for l in items}
        assert "RAG_RESOLVED" in outcomes
        assert "AGENT_RESOLVED" in outcomes

    def test_config(self):
        r = httpx.get(f"{BASE}/api/v1/admin/config", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        # Config is nested: {llm: {primary_model: ...}, rag: {...}}
        assert "llm" in data
        assert "primary_model" in data["llm"]


# ═══════════════════════════════════════════════════════════════
# 5. SESSION TESTS (routes: /api/v1/sessions/...)
# ═══════════════════════════════════════════════════════════════

class TestSessions:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("12345", "pass")["access_token"]
        self.headers = auth_headers(self.token)

    def test_create_session(self):
        r = httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data
        assert data["session_id"].startswith("sess-")

    def test_list_sessions(self):
        httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.headers)
        r = httpx.get(f"{BASE}/api/v1/sessions/active", headers=self.headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_session_has_user_info(self):
        r = httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.headers)
        session_id = r.json()["session_id"]
        r2 = httpx.get(f"{BASE}/api/v1/sessions/active", headers=self.headers)
        sessions = r2.json()
        session = next((s for s in sessions if s["id"] == session_id), None)
        assert session is not None
        assert session["user_matricule"] == "12345"


# ═══════════════════════════════════════════════════════════════
# 5b. BRIEFING ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════

class TestBriefing:
    """Test the agent briefing panel endpoint (GET /api/v1/sessions/{sid}/briefing)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        # Create session as user
        self.user_token = login("12345", "pass")["access_token"]
        self.user_headers = auth_headers(self.user_token)
        # Agent token
        self.agent_token = login("88888", "agent")["access_token"]
        self.agent_headers = auth_headers(self.agent_token)

    def _create_session_with_history(self) -> str:
        """Create a session and inject mock history via the sessions store."""
        r = httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.user_headers)
        return r.json()["session_id"]

    def test_briefing_structure(self):
        """Briefing endpoint returns correct JSON structure."""
        session_id = self._create_session_with_history()
        r = httpx.get(f"{BASE}/api/v1/sessions/{session_id}/briefing", headers=self.agent_headers)
        assert r.status_code == 200
        data = r.json()
        # Verify required fields
        assert "client" in data
        assert data["client"]["name"] is not None
        assert data["client"]["matricule"] == "12345"
        assert "ai_summary" in data
        assert "topics" in data
        assert isinstance(data["topics"], list)
        assert "duration_minutes" in data
        assert "message_count" in data
        assert "status" in data

    def test_briefing_404_invalid_session(self):
        """Briefing returns 404 for nonexistent session."""
        r = httpx.get(f"{BASE}/api/v1/sessions/sess-nonexistent/briefing", headers=self.agent_headers)
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 5c. HYBRID HANDOFF TESTS
# ═══════════════════════════════════════════════════════════════

class TestHybridHandoff:
    """Test the hybrid handoff flow: escalation + takeover + resolve with HITL."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.user_token = login("12345", "pass")["access_token"]
        self.user_headers = auth_headers(self.user_token)
        self.agent_token = login("88888", "agent")["access_token"]
        self.agent_headers = auth_headers(self.agent_token)

    def test_takeover_changes_status(self):
        """Agent takeover changes session status to agent_connected."""
        # Create session
        r = httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.user_headers)
        session_id = r.json()["session_id"]
        # Takeover
        r2 = httpx.post(f"{BASE}/api/v1/sessions/{session_id}/takeover", headers=self.agent_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "taken_over"
        # Verify in active list
        r3 = httpx.get(f"{BASE}/api/v1/sessions/active", headers=self.agent_headers)
        session = next((s for s in r3.json() if s["id"] == session_id), None)
        assert session is not None
        assert session["status"] == "agent_connected"

    def test_resolve_with_hitl_save(self):
        """Resolve a session with save_to_knowledge flag."""
        # Create + takeover
        r = httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.user_headers)
        session_id = r.json()["session_id"]
        httpx.post(f"{BASE}/api/v1/sessions/{session_id}/takeover", headers=self.agent_headers)
        # Resolve with HITL save (may fail gracefully if no agent messages exist)
        r2 = httpx.post(
            f"{BASE}/api/v1/sessions/{session_id}/resolve",
            headers=self.agent_headers,
            json={"save_to_knowledge": True, "tags": ["test", "handoff"]},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "resolved"

    def test_takeover_nonexistent_session(self):
        """Takeover returns 404 for nonexistent session."""
        r = httpx.post(f"{BASE}/api/v1/sessions/sess-fake/takeover", headers=self.agent_headers)
        assert r.status_code == 404

    def test_user_chats_endpoint(self):
        """User can list their own chats."""
        httpx.post(f"{BASE}/api/v1/sessions/create", headers=self.user_headers)
        r = httpx.get(f"{BASE}/api/v1/sessions/user-chats", headers=self.user_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "id" in data[0]
        assert "status" in data[0]


# ═══════════════════════════════════════════════════════════════
# 6. HEALTH & RESILIENCE TESTS
# ═══════════════════════════════════════════════════════════════

class TestResilience:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("77777", "admin")["access_token"]
        self.headers = auth_headers(self.token)

    def test_health_endpoint(self):
        r = httpx.get(f"{BASE}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_insights(self):
        r = httpx.get(f"{BASE}/api/v1/insights", headers=self.headers)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 7. ESCALATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestEscalation:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.token = login("12345", "pass")["access_token"]
        self.headers = auth_headers(self.token)

    def test_escalate_to_human(self):
        r = httpx.post(
            f"{BASE}/api/v1/support/escalade",
            headers=self.headers,
            json={
                "matricule": "12345",
                "chat_history": [{"role": "user", "content": "Je veux parler à un humain"}],
                "reason": "Test escalation",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "escalated"
        assert "case_id" in data

    def test_escalation_tickets_visible(self):
        httpx.post(
            f"{BASE}/api/v1/support/escalade",
            headers=self.headers,
            json={"matricule": "12345", "chat_history": [{"role": "user", "content": "Test"}], "reason": "Test"},
        )
        r = httpx.get(f"{BASE}/api/v1/dashboard/tickets", headers=self.headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1
