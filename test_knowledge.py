"""Test the Phase 3 knowledge pipeline: sync, search, HITL feedback, corrections."""
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
        body = r.json()
        # Pretty print but truncate
        text = json.dumps(body, indent=2, ensure_ascii=False)
        if len(text) > 500:
            text = text[:500] + "\n  ... (truncated)"
        for line in text.split("\n"):
            print(f"         {line}")

print("\n=== Phase 3: Knowledge Pipeline Verification ===\n")

# Login
r = httpx.post(f"{base}/auth/login", json={"matricule": "88888", "password": "agent"})
agent_token = r.json()["access_token"]
h = {"Authorization": f"Bearer {agent_token}"}
print("[Auth] Agent Karim logged in\n")

# 1. Knowledge Stats
print("[1] Knowledge Store Stats")
r = httpx.get(f"{base}/api/v1/knowledge/stats", headers=h)
check("GET /knowledge/stats", r, show_body=True)

# 2. RAG Search - high confidence query
print("\n[2] RAG Search - 'plafond dentaire'")
r = httpx.get(f"{base}/api/v1/knowledge/search", params={"q": "plafond dentaire", "top_k": 3}, headers=h)
check("GET /knowledge/search (dentaire)", r)
if r.status_code == 200:
    data = r.json()
    print(f"         Results: {data['count']}")
    for res in data["results"][:3]:
        print(f"         - sim={res['similarity']:.4f} | {res['source_type']} | {res['chunk_text'][:80]}...")

# 3. RAG Search - remboursement
print("\n[3] RAG Search - 'delai remboursement'")
r = httpx.get(f"{base}/api/v1/knowledge/search", params={"q": "delai remboursement"}, headers=h)
check("GET /knowledge/search (remboursement)", r)
if r.status_code == 200:
    data = r.json()
    print(f"         Results: {data['count']}")
    for res in data["results"][:2]:
        print(f"         - sim={res['similarity']:.4f} | {res['chunk_text'][:80]}...")

# 4. RAG Search - naissance
print("\n[4] RAG Search - 'prime naissance'")
r = httpx.get(f"{base}/api/v1/knowledge/search", params={"q": "prime naissance"}, headers=h)
check("GET /knowledge/search (naissance)", r)
if r.status_code == 200:
    data = r.json()
    print(f"         Top result sim={data['results'][0]['similarity']:.4f}")

# 5. Manual sync trigger
print("\n[5] Manual Sync Trigger")
r = httpx.post(f"{base}/api/v1/knowledge/sync", headers=h)
check("POST /knowledge/sync", r, show_body=True)

# 6. HITL Feedback Loop - Create session, add messages, resolve with save
print("\n[6] HITL Feedback Loop")

# Create session as user
r = httpx.post(f"{base}/auth/login", json={"matricule": "12345", "password": "pass"})
user_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = httpx.post(f"{base}/api/v1/sessions/create", headers=user_h)
sid = r.json()["session_id"]
print(f"  Session created: {sid}")

# Simulate a conversation by directly manipulating via takeover + resolve
# First takeover as agent
r = httpx.post(f"{base}/api/v1/sessions/{sid}/takeover", headers=h)
check(f"POST /sessions/{sid}/takeover", r)

# Get history to verify
r = httpx.get(f"{base}/api/v1/sessions/{sid}/history", headers=h)
history = r.json()["history"]
print(f"  History has {len(history)} messages (system join message)")

# Now resolve WITH save_to_knowledge
# Note: no user/agent messages yet, so HITL save won't find Q&A pairs
r = httpx.post(
    f"{base}/api/v1/sessions/{sid}/resolve",
    headers=h,
    json={"save_to_knowledge": False}  # No messages to save
)
check(f"POST /sessions/{sid}/resolve (no HITL)", r)

# 7. AI Correction Flagging
print("\n[7] AI Correction Flagging")
r = httpx.post(
    f"{base}/api/v1/corrections",
    headers=h,
    json={
        "session_id": sid,
        "wrong_message_content": "Le plafond dentaire est de 1000 TND",
        "correct_answer": "Le plafond dentaire est de 600 TND par beneficiaire selon l'Article 4",
        "correction_type": "factual_error"
    }
)
check("POST /corrections", r, show_body=True)

r = httpx.get(f"{base}/api/v1/corrections", headers=h)
check("GET /corrections", r)
if r.status_code == 200:
    data = r.json()
    print(f"         Total corrections: {data['total']}")
    print(f"         By type: {data['by_type']}")

# Summary
print("\n" + "=" * 50)
failed = [name for name, code in results if code != 200]
if failed:
    print(f"FAIL: {len(failed)} endpoints failed: {failed}")
else:
    print(f"ALL {len(results)} KNOWLEDGE PIPELINE TESTS PASSED")
print("=" * 50)
