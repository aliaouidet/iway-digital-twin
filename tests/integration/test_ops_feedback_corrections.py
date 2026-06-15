"""Integration tests for monitoring /ops, CSAT feedback, and the corrections flow
(persist via FakeDB + best-effort worker dispatch)."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")


def test_ops_snapshot_ok(client, auth_headers):
    r = client.get("/api/v1/monitoring/ops", headers=auth_headers("Admin"))
    assert r.status_code == 200
    body = r.json()
    assert "tokens" in body and "circuits" in body and "cache" in body


def test_feedback_post_and_stats(client, auth_headers):
    from backend.services.session_store import SESSIONS
    SESSIONS["sess-1"] = {"id": "sess-1", "status": "resolved", "history": []}
    p = client.post("/api/v1/sessions/sess-1/feedback",
                    json={"rating": "positive"}, headers=auth_headers("Adherent"))
    assert p.status_code == 200
    s = client.get("/api/v1/feedback/stats", headers=auth_headers("Admin"))
    assert s.status_code == 200
    stats = s.json()
    assert stats["total"] >= 1 and stats["positive"] >= 1


def test_correction_flagged_returns_ok_and_lists(client, auth_headers):
    r = client.post("/api/v1/corrections", json={
        "session_id": "test-session",
        "wrong_message_content": "Le plafond est de 9999 TND.",
        "correct_answer": "Le plafond dentaire est de 600 TND par an.",
        "correction_type": "factual_error",
    }, headers=auth_headers("Agent"))
    assert r.status_code == 200
    assert r.json()["status"] == "flagged"

    lst = client.get("/api/v1/corrections", headers=auth_headers("Admin"))
    assert lst.status_code == 200
    assert lst.json()["total"] >= 1


def test_correction_forbidden_for_adherent(client, auth_headers):
    r = client.post("/api/v1/corrections", json={
        "session_id": "s", "wrong_message_content": "x", "correct_answer": "y",
    }, headers=auth_headers("Adherent"))
    assert r.status_code == 403
