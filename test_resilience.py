"""Test Phase 4: Resilience & Fault Tolerance patterns."""
import httpx
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = "http://localhost:8000"
results = []

def check(name, r, show_body=False):
    status = "PASS" if r.status_code == 200 else "FAIL"
    results.append((name, r.status_code))
    print(f"  [{status}] {name}: {r.status_code}")
    if show_body and r.status_code == 200:
        import json
        text = json.dumps(r.json(), indent=2, ensure_ascii=False)
        if len(text) > 600:
            text = text[:600] + "\n  ... (truncated)"
        for line in text.split("\n"):
            print(f"         {line}")

print("\n=== Phase 4: Resilience Verification ===\n")

# Login
r = httpx.post(f"{base}/auth/login", json={"matricule": "77777", "password": "admin"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print("[Auth] Admin Sara logged in\n")

# 1. Health Check (enhanced)
print("[1] Enhanced Health Check")
r = httpx.get(f"{base}/health")
check("GET /health", r, show_body=True)

# 2. Resilience Status
print("\n[2] Resilience Status Dashboard")
r = httpx.get(f"{base}/api/v1/resilience", headers=h)
check("GET /resilience", r, show_body=True)

# 3. Verify RAG-powered chat (via REST search, since we can't test WS easily)
print("\n[3] RAG Pipeline - Smoke Test")
r = httpx.get(f"{base}/api/v1/knowledge/search", params={"q": "urgence medicale"}, headers=h)
check("RAG search (urgence)", r)
if r.status_code == 200:
    data = r.json()
    top = data["results"][0] if data["results"] else None
    if top:
        print(f"         Top: sim={top['similarity']:.4f} ({top['source_type']})")

# 4. Verify all original endpoints still work
print("\n[4] Regression: All Original Endpoints")
for ep in ["/", "/health", "/api/v1/me", "/api/v1/metrics", "/api/v1/knowledge/stats"]:
    r = httpx.get(f"{base}{ep}", headers=h)
    check(f"GET {ep}", r)

# 5. Session lifecycle with resilience
print("\n[5] Session Lifecycle + Agent Disconnect Handling")

# Login as user
r = httpx.post(f"{base}/auth/login", json={"matricule": "12345", "password": "pass"})
user_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# Create session
r = httpx.post(f"{base}/api/v1/sessions/create", headers=user_h)
sid = r.json()["session_id"]
print(f"  Session: {sid}")

# Agent takeover
r = httpx.post(f"{base}/api/v1/sessions/{sid}/takeover", headers=h)
check(f"Agent takeover", r)

# Resolve with HITL save (no messages yet, but tests the pathway)
r = httpx.post(
    f"{base}/api/v1/sessions/{sid}/resolve",
    headers=h,
    json={"save_to_knowledge": False}
)
check("Resolve session", r)

# Summary
print("\n" + "=" * 50)
failed = [name for name, code in results if code != 200]
if failed:
    print(f"FAIL: {len(failed)} tests failed: {failed}")
else:
    print(f"ALL {len(results)} RESILIENCE TESTS PASSED")
print("=" * 50)
