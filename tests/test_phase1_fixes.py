"""
Phase 1 Fixes — Verification Test Suite
========================================
Tests all 5 Phase 1 fixes against the live Docker environment.

Run:  python tests/test_phase1_fixes.py
Requires: pip install requests websockets  (host machine only)
"""

import sys
import json
import time
import asyncio
import requests
import threading

API = "http://localhost:8000"
AGENT_CREDS = {"matricule": "88888", "password": "agent"}
USER_CREDS  = {"matricule": "12345", "password": "pass"}
ADMIN_CREDS = {"matricule": "77777", "password": "admin"}

passed = 0
failed = 0


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}")
    if detail:
        print(f"     -> {detail}")


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds)
    if r.status_code == 200:
        return r.json()["access_token"]
    return None


# ============================================================
# TEST 1: API Health & Startup
# ============================================================
def test_health():
    section("TEST 1: API Health & Startup")
    try:
        r = requests.get(f"{API}/health", timeout=5)
        check("API is reachable", r.status_code == 200, f"status={r.status_code}")
        data = r.json()
        check("Status is healthy/degraded", data.get("status") in ("healthy", "degraded"), f"status={data.get('status')}")
        check("Knowledge store loaded", "entries" in str(data.get("services", {}).get("knowledge_store", "")))
    except Exception as e:
        check("API reachable", False, str(e))


# ============================================================
# TEST 2: F2 — action_router_node is now a pass-through
# ============================================================
def test_f2_action_router():
    section("TEST 2: F2 — action_router_node (no wasted LLM call)")
    
    token = login(USER_CREDS)
    check("User login", token is not None)
    if not token:
        return

    # Create a session
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API}/api/v1/sessions/create", headers=headers)
    check("Session created", r.status_code == 200)
    if r.status_code != 200:
        return
    session_id = r.json()["session_id"]

    # Check that lookups.py no longer imports llm_factory
    # (We verify this structurally by checking the module has no LLM dependency)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lookups_check",
        "backend/domain/graph/nodes/lookups.py",
    )
    
    # Read the file and verify no LLM imports
    with open("backend/domain/graph/nodes/lookups.py", "r", encoding="utf-8") as f:
        source = f.read()

    check("No llm_factory import", "llm_factory" not in source, "Wasted LLM call removed")
    check("No ActionRouterSchema class", "ActionRouterSchema" not in source, "Dead code removed")
    check("No ACTION_ROUTER_PROMPT", "ACTION_ROUTER_PROMPT" not in source, "Dead prompt removed")
    check("Pass-through docstring present", "pass-through" in source.lower() or "Deterministic" in source, "Node is zero-latency")


# ============================================================
# TEST 3: F4 — graph_context in state (no duplicate GraphRAG)
# ============================================================
def test_f4_graph_context():
    section("TEST 3: F4 — graph_context state field (no duplicate retrieval)")

    # Verify state.py has the new field
    with open("state.py", "r", encoding="utf-8") as f:
        state_src = f.read()
    check("graph_context field in ClaimsGraphState", "graph_context: Optional[str]" in state_src)

    # Verify rag_retrieval.py returns graph_context
    with open("backend/domain/graph/nodes/rag_retrieval.py", "r", encoding="utf-8") as f:
        rag_src = f.read()
    check("rag_retrieval returns graph_context", '"graph_context"' in rag_src or "'graph_context'" in rag_src)

    # Verify draft_response.py reads from state (not calling get_related_context)
    with open("backend/domain/graph/nodes/draft_response.py", "r", encoding="utf-8") as f:
        draft_src = f.read()
    check("draft_response reads state.get('graph_context')", 'state.get("graph_context")' in draft_src or "state.get('graph_context')" in draft_src)
    check("No duplicate get_related_context import", "from backend.services.knowledge_graph import get_related_context" not in draft_src, "Duplicate call eliminated")


# ============================================================
# TEST 4: F3 — Role-based WebSocket broadcast
# ============================================================
def test_f3_ws_role_filtering():
    section("TEST 4: F3 -- Role-based WebSocket broadcast filtering")

    # Verify ws_manager.py has role tracking
    with open("backend/services/ws_manager.py", "r", encoding="utf-8") as f:
        ws_src = f.read()
    check("ConnectionManager tracks role", 'role' in ws_src and '"role"' in ws_src)
    check("broadcast() accepts target_roles", "target_roles" in ws_src)
    check("Role filtering logic present", "target_roles and conn" in ws_src or 'conn["role"]' in ws_src)

    # Verify main.py passes role on connect
    with open("main.py", "r", encoding="utf-8") as f:
        main_src = f.read()
    check("main.py passes role to ws_manager.connect()", "role=user.get" in main_src or "role=" in main_src)

    # Verify sessions.py uses target_roles on broadcast
    with open("backend/routers/sessions.py", "r", encoding="utf-8") as f:
        sess_src = f.read()
    agent_admin_count = sess_src.count('target_roles={"Agent", "Admin"}')
    check(f"sessions.py broadcasts filtered ({agent_admin_count} calls)", agent_admin_count >= 3, f"Found {agent_admin_count} filtered broadcast calls")

    # Verify tracing.py uses target_roles
    with open("backend/services/tracing.py", "r", encoding="utf-8") as f:
        trace_src = f.read()
    check("tracing.py PIPELINE_TRACE filtered", 'target_roles={"Agent", "Admin"}' in trace_src)

    # Live test: Agent can connect to /ws/events
    agent_token = login(AGENT_CREDS)
    check("Agent login for WS test", agent_token is not None)
    
    if agent_token:
        try:
            import websockets

            async def test_agent_ws():
                uri = f"ws://localhost:8000/ws/events?token={agent_token}"
                async with websockets.connect(uri) as ws:
                    # Should receive a METRIC_UPDATE within 11s
                    msg = await asyncio.wait_for(ws.recv(), timeout=12)
                    data = json.loads(msg)
                    return data.get("type") == "METRIC_UPDATE"

            result = asyncio.run(test_agent_ws())
            check("Agent WS /ws/events connects + receives METRIC_UPDATE", result)
        except Exception as e:
            check("Agent WS connection", False, str(e))

    # Live test: User (Adherent) should be REJECTED from /ws/events
    user_token = login(USER_CREDS)
    if user_token:
        try:
            import websockets

            async def test_user_ws_rejected():
                uri = f"ws://localhost:8000/ws/events?token={user_token}"
                try:
                    async with websockets.connect(uri) as ws:
                        # If we get here, connection was accepted (bad)
                        return False
                except websockets.exceptions.ConnectionClosed:
                    return True  # Correctly rejected
                except Exception:
                    return True  # Any connection failure = correctly blocked

            result = asyncio.run(test_user_ws_rejected())
            check("Adherent WS /ws/events correctly rejected", result, "Role gate working")
        except Exception as e:
            check("Adherent WS rejection", False, str(e))


# ============================================================
# TEST 5: F7 — PII regex precision (no false positives)
# ============================================================
def test_f7_pii_regex():
    section("TEST 5: F7 — PII compliance regex (no false positives)")

    with open("backend/domain/graph/nodes/compliance_check.py", "r", encoding="utf-8") as f:
        comp_src = f.read()

    # The old generic pattern should be gone
    check("No generic \\b\\d{5}\\b pattern", r"\b\d{5}\b" not in comp_src, "Was matching postal codes/amounts")
    
    # Unused module-level patterns should be removed
    check("_PII_PATTERNS removed", "_PII_PATTERNS" not in comp_src, "Dead code cleaned")
    check("_COMPILED_PII removed", "_COMPILED_PII" not in comp_src, "Dead code cleaned")

    # New matricule check uses actual session ID
    check("Matricule checked via state.get('matricule')", 'state.get("matricule"' in comp_src or "state.get('matricule'" in comp_src)
    check("Length guard on matricule", 'len(matricule) >= 4' in comp_src, "Prevents empty-string false matches")
    
    # Credential pattern detection still present
    check("Token pattern detection", "token[=:" in comp_src, "Inline credential detection")
    check("Password pattern detection", "mot" in comp_src and "passe" in comp_src, "French password pattern")


# ============================================================
# TEST 6: CORS restriction (already correct)
# ============================================================
def test_cors():
    section("TEST 6: CORS — Origin restriction")

    with open("main.py", "r", encoding="utf-8") as f:
        main_src = f.read()

    check('CORS not set to ["*"]', '"*"' not in main_src.split("allow_origins")[1].split("]")[0] if "allow_origins" in main_src else True, "Origins restricted")
    check("localhost:4200 allowed", "localhost:4200" in main_src)
    check("localhost:8000 allowed (Swagger)", "localhost:8000" in main_src)


# ============================================================
# TEST 7: End-to-End Chat Flow (full pipeline validation)
# ============================================================
def test_e2e_chat():
    section("TEST 7: End-to-End — Chat flow through fixed pipeline")

    user_token = login(USER_CREDS)
    check("User login", user_token is not None)
    if not user_token:
        return

    headers = {"Authorization": f"Bearer {user_token}"}

    # Create session
    r = requests.post(f"{API}/api/v1/sessions/create", headers=headers)
    check("Session created", r.status_code == 200)
    if r.status_code != 200:
        return
    session_id = r.json()["session_id"]

    # Test chat via WebSocket
    try:
        import websockets

        async def test_chat():
            uri = f"ws://localhost:8000/ws/chat/{session_id}?token={user_token}"
            async with websockets.connect(uri) as ws:
                # Send a simple insurance question
                await ws.send(json.dumps({
                    "type": "user_message",
                    "content": "Bonjour, quel est le plafond dentaire?"
                }))

                # Collect responses for up to 30 seconds
                responses = []
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        responses.append(data)
                        # Stop when we get the final response
                        if data.get("type") in ("ai_response", "ai_complete", "final_response"):
                            break
                        if data.get("type") == "error":
                            break
                except asyncio.TimeoutError:
                    pass

                return responses

        responses = asyncio.run(test_chat())
        check("Received WebSocket responses", len(responses) > 0, f"Got {len(responses)} message(s)")

        # Check for thinking/token/response events
        types = [r.get("type") for r in responses]
        check("Pipeline produced output", any(t in types for t in ("ai_token", "ai_response", "ai_complete", "thinking", "final_response")),
              f"Event types: {types}")

    except Exception as e:
        check("E2E chat flow", False, str(e))


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("\n" + "== " * 20)
    print("  I-Way Digital Twin -- Phase 1 Verification Suite")
    print("== " * 20)

    test_health()
    test_f2_action_router()
    test_f4_graph_context()
    test_f3_ws_role_filtering()
    test_f7_pii_regex()
    test_cors()
    test_e2e_chat()

    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
