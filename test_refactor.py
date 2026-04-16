"""Quick verification that all API endpoints work after modular refactor."""
import httpx

base = "http://localhost:8000"
results = []

def check(name, r):
    status = "✅" if r.status_code == 200 else "❌"
    results.append((name, r.status_code))
    print(f"  {status} {name}: {r.status_code}")

print("\n=== I-Way Modular Backend Verification ===\n")

# Public endpoints
print("[Public]")
r = httpx.get(f"{base}/")
check("GET /", r)
print(f"     version={r.json().get('version')}, arch={r.json().get('architecture')}")

r = httpx.get(f"{base}/health")
check("GET /health", r)

# Auth - all 4 personas
print("\n[Auth]")
personas = [
    ("12345", "pass", "Adherent"),
    ("99999", "med", "Prestataire"),
    ("88888", "agent", "Agent"),
    ("77777", "admin", "Admin"),
]
tokens = {}
for mat, pw, role in personas:
    r = httpx.post(f"{base}/auth/login", json={"matricule": mat, "password": pw})
    check(f"POST /auth/login ({role})", r)
    if r.status_code == 200:
        tokens[role] = r.json()["access_token"]
        actual_role = r.json()["user"]["role"]
        assert actual_role == role, f"Expected {role}, got {actual_role}"

r = httpx.get(f"{base}/auth/public-key")
check("GET /auth/public-key", r)

# Protected endpoints (using Adherent token)
print("\n[Protected - Adherent]")
h = {"Authorization": f"Bearer {tokens['Adherent']}"}
endpoints = [
    "GET /api/v1/me",
    "GET /api/v1/adherent/dossiers",
    "GET /api/v1/adherent/beneficiaires",
    "GET /api/v1/prestations",
    "GET /api/v1/remboursements",
    "GET /api/v1/reclamations",
    "GET /api/v1/knowledge-base",
]
for ep in endpoints:
    method, path = ep.split(" ", 1)
    r = httpx.get(f"{base}{path}", headers=h)
    check(ep, r)

# Dashboard endpoints (using Admin token)
print("\n[Dashboard - Admin]")
h_admin = {"Authorization": f"Bearer {tokens['Admin']}"}
for ep in ["GET /api/v1/metrics", "GET /api/v1/logs", "GET /api/v1/insights", "GET /api/v1/admin/config", "GET /api/v1/dashboard/tickets"]:
    method, path = ep.split(" ", 1)
    r = httpx.get(f"{base}{path}", headers=h_admin)
    check(ep, r)

# Session management
print("\n[Sessions]")
r = httpx.post(f"{base}/api/v1/sessions/create", headers=h)
check("POST /sessions/create", r)
sid = r.json()["session_id"]
print(f"     session_id={sid}")

r = httpx.get(f"{base}/api/v1/sessions/active", headers=h)
check("GET /sessions/active", r)
print(f"     active_count={len(r.json())}")

r = httpx.get(f"{base}/api/v1/sessions/{sid}/history", headers=h)
check(f"GET /sessions/{sid}/history", r)

# Summary
print("\n" + "=" * 45)
failed = [name for name, code in results if code != 200]
if failed:
    print(f"❌ {len(failed)} FAILED: {failed}")
else:
    print(f"✅ ALL {len(results)} ENDPOINTS VERIFIED SUCCESSFULLY")
print("=" * 45)
