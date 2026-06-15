"""Integration tests for the knowledge curation API: role guards, PII redaction on
save, and the lifecycle-status health snapshot."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

import pytest
from backend.services import rag_service


@pytest.fixture
def stub_add(monkeypatch):
    captured = {}
    async def _fake(session_id, question, answer, agent_matricule="", agent_name="", **kw):
        captured.update({"question": question, "answer": answer, **kw})
        return {"status": "added", "source_id": "hitl-x"}
    monkeypatch.setattr(rag_service, "async_add_hitl_with_dedup", _fake)
    return captured


def test_articles_forbidden_for_adherent(client, auth_headers, stub_add):
    r = client.post("/api/v1/knowledge/articles",
                    json={"question": "Q?", "answer": "Une réponse.", "topic": "T"},
                    headers=auth_headers("Adherent"))
    assert r.status_code == 403


def test_articles_admin_ok_and_redacts_identifiers(client, auth_headers, stub_add):
    r = client.post("/api/v1/knowledge/articles",
                    json={"question": "Mon CIN 09876543 ?",
                          "answer": "Votre CIN 09876543 figure au dossier.", "topic": "T"},
                    headers=auth_headers("Admin"))
    assert r.status_code == 200
    # redact_identifiers ran before embedding — long id is masked.
    assert "09876543" not in stub_add["answer"]
    assert stub_add["origin"] == "insights"


def test_health_empty_ok(client, auth_headers):
    # Default FakeDB → empty GROUP BY → zeros (no Postgres needed).
    r = client.get("/api/v1/knowledge/health", headers=auth_headers("Admin"))
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_health_forbidden_for_adherent(client, auth_headers):
    assert client.get("/api/v1/knowledge/health",
                      headers=auth_headers("Adherent")).status_code == 403
