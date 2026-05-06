# I-Way Digital Twin — Future Upgrades Roadmap

> **Created**: 2026-05-04
> **Status**: Saved for future implementation. Tell the AI assistant "proceed with Phase X" when ready.
> **Note on 2.1**: Redis caching for RAG queries is NOT yet implemented. The existing caching is only `lru_cache` on settings and lazy-loaded embedding model — no query-level Redis cache exists yet.

---

## Phase 1 — Security Hardening (1-2 days)

- [ ] **1.1** Revoke exposed `GOOGLE_API_KEY` from `.env`, purge from git history
- [ ] **1.2** Add bcrypt password hashing for mock users + `DEMO_MODE` flag
- [ ] **1.3** Restrict CORS to `http://localhost:4200` + `ALLOWED_ORIGINS` env var
- [ ] **1.4** Add `REQUIRE_WS_AUTH` env var — reject unauthenticated WS in prod
- [ ] **1.5** Add non-root user in Dockerfile, remove `user: root` from docker-compose

---

## Phase 2 — Data Architecture (2-3 days)

- [ ] **3.1** Migrate `SESSIONS` dict to Redis as primary store (PostgreSQL as source of truth)
- [ ] **3.2** Migrate `SYSTEM_LOGS` to Redis/PostgreSQL (use existing `AuditLog` table)
- [ ] **3.3** Add TTL-based cleanup for `_session_locks` (evict after 2h idle)
- [ ] **3.4** Reset ephemeral state fields (`rag_confidence`, `system_records`, `sub_intents`, `sub_intent_results`) in `graph_executor.py` before each invocation

---

## Phase 3 — AI Pipeline Optimization (2 days)

- [ ] **2.1** Add Redis-backed LRU cache for RAG query embeddings (TTL: 1h) + top-k result caching
- [ ] **2.2** Add regex pre-filter for small_talk patterns in `decompose_node` (skip LLM call for "Bonjour", "Merci", etc.)
- [ ] **2.3** Remove artificial streaming delays (`asyncio.sleep`) for non-LLM RAG/simulated responses
- [ ] **2.4** Add embedding model upgrade path (auto-detect dimensions, re-embed migration script)
- [ ] **2.5** Send last 6 messages as conversation history to `draft_response_node` (not just the last one)

---

## Phase 4 — Code Quality (2-3 days)

- [ ] **5.1** Split `chat_service.py` (675L) into: `chat_handler.py`, `ai_response.py`, `escalation_handler.py`, `streaming.py`
- [ ] **5.2** Add Alembic for database schema migrations
- [ ] **5.3** Define Pydantic models for all WebSocket message types
- [ ] **5.4** Move `state.py` → `backend/domain/state.py`, audit/remove `bot_tools.py`
- [ ] **5.5** Split `iway_mock.py` (26KB) into `mock_data.py` + `mock_routes.py`

---

## Phase 5 — Observability & Resilience (1-2 days)

- [ ] **4.1** Add rate limiting (`slowapi` or Redis-based): 10/min login, 30/min chat
- [ ] **4.2** Switch to structured JSON logging (`structlog`) with session_id/trace_id
- [ ] **4.3** Deepen health check: real DB `SELECT 1` + Redis `PING`
- [ ] **4.4** Add Prometheus metrics endpoint + Grafana dashboard config
- [ ] **4.5** Add per-user WebSocket connection limits (max 5/user, 200 total)

---

## Phase 6 — Testing (2 days)

- [ ] **8.1** Add unit tests for: graph routing, confidence fusion, circuit breaker, RAG search, decompose parsing
- [ ] **8.2** Add load testing script (locust/k6): 50 concurrent WS sessions
- [ ] **8.3** Document WS protocol schema + contract tests

---

## Phase 7 — Frontend (2 days)

- [ ] **6.1** Add global error boundary + WS reconnection with exponential backoff
- [ ] **6.2** Add message retry queue (pending messages in localStorage)
- [ ] **6.3** Add "User is typing..." indicators
- [ ] **6.4** Verify dark mode persistence via localStorage
- [ ] **6.5** Add ARIA labels, keyboard nav, screen reader support

---

## Phase 8 — DevOps (1 day)

- [ ] **7.1** Add `.dockerignore` (exclude `.git`, `.venv`, `node_modules`, etc.)
- [ ] **7.2** Multi-stage Dockerfile (build + slim runtime image)
- [ ] **7.3** Docker Compose profiles (`dev` vs `prod`)
- [ ] **7.4** Add GitHub Actions CI: lint, typecheck, test, build
- [ ] **7.5** Add pre-commit hooks (ruff, mypy, isort, black, eslint, prettier)
