"""Integration tests for role-based access control on the admin config endpoint."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")


def test_config_get_allowed_for_agent_and_admin(client, auth_headers):
    assert client.get("/api/v1/admin/config", headers=auth_headers("Agent")).status_code == 200
    assert client.get("/api/v1/admin/config", headers=auth_headers("Admin")).status_code == 200


def test_config_get_forbidden_for_adherent(client, auth_headers):
    assert client.get("/api/v1/admin/config", headers=auth_headers("Adherent")).status_code == 403


def test_config_put_admin_only(client, auth_headers):
    body = {"rag": {"top_k": 4}}
    assert client.put("/api/v1/admin/config", json=body, headers=auth_headers("Agent")).status_code == 403
    ok = client.put("/api/v1/admin/config", json=body, headers=auth_headers("Admin"))
    assert ok.status_code == 200
    assert ok.json()["config"]["rag"]["top_k"] == 4


def test_unauthenticated_rejected(client):
    assert client.get("/api/v1/admin/config").status_code in (401, 403)
