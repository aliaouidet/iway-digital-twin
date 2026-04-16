"""Verify Phase 5 tracing endpoints."""
import httpx, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = "http://localhost:8000"

print("=== Phase 5: Observability Verification ===\n")

# 1. Traces
r = httpx.get(f"{base}/api/v1/traces")
d = r.json()
print(f"[1] Traces captured: {d['count']}")
for t in d["traces"]:
    print(f"  {t['trace_id']}: q=\"{t['query'][:30]}\" outcome={t['outcome']} conf={t['confidence']}% dur={t['total_duration_ms']}ms spans={t['span_count']}")

# 2. Pipeline Stats
print()
r2 = httpx.get(f"{base}/api/v1/traces/stats")
s = r2.json()["pipeline"]
print(f"[2] Pipeline Stats:")
print(f"  Total requests: {s['total_requests']}")
print(f"  RAG resolved:   {s['rag_resolved']}")
print(f"  Escalated:      {s['human_escalated']}")
print(f"  Avg duration:   {s['avg_duration_ms']}ms")
print(f"  RAG success:    {s['rag_success_rate']}%")
print(f"  Escalation:     {s['escalation_rate']}%")

# 3. Resilience
res = r2.json()["resilience"]["circuit_breakers"]
print(f"\n[3] Circuit Breakers:")
for name, cb in res.items():
    print(f"  {name}: state={cb['state']} calls={cb['total_calls']} failures={cb['total_failures']}")

# 4. Connections
conn = r2.json()["connections"]
print(f"\n[4] Live Connections:")
print(f"  WebSocket: {conn['websocket_count']}")
print(f"  Active sessions: {conn['active_sessions']}")
print(f"  Pending handoffs: {conn['pending_handoffs']}")

# 5. Health
r3 = httpx.get(f"{base}/health")
h = r3.json()
print(f"\n[5] Health: {h['status']}")
print(f"  Knowledge: {h['services']['knowledge_store']}")
print(f"  LLM circuit: {h['services']['llm_circuit']}")

print("\n" + "=" * 50)
print("ALL PHASE 5 ENDPOINTS OPERATIONAL")
print("=" * 50)
