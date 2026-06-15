"""
Shared fixtures for the offline test suite.

Every backend test runs WITHOUT the LAN, Postgres, Redis, or a real LLM. We
stub the SOAP layer, the DB session factory + repositories, and the LLM — the
same approach as test_auth_activation.py, lifted here so it is reusable.

The integration `client` fixture builds a BARE FastAPI app with the routers
(no main.py lifespan: that warms the semantic router, hydrates the DB, and
builds the graph — none of which we want in a unit run). Auth is exercised for
real via short-lived RS256 tokens from a throwaway keypair.
"""

import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Demo personas (match MOCK_USERS in routers/auth.py) ──
ROLE_MATRICULE = {"Adherent": "12345", "Prestataire": "99999", "Agent": "88888", "Admin": "77777"}


# ──────────────────────────────────────────────────────────────
# JWT keys + tokens
# ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _rsa_keys(tmp_path_factory):
    """Generate a throwaway RSA keypair so the auth dependencies verify real tokens."""
    from backend.routers import auth
    auth.init_keys(str(tmp_path_factory.mktemp("jwt_keys")))


@pytest.fixture
def make_token():
    from backend.routers.auth import create_jwt

    def _make(role: str = "Admin") -> str:
        return create_jwt(ROLE_MATRICULE.get(role, "77777"), role)
    return _make


@pytest.fixture
def auth_headers(make_token):
    def _headers(role: str = "Admin") -> dict:
        return {"Authorization": f"Bearer {make_token(role)}"}
    return _headers


# ──────────────────────────────────────────────────────────────
# Fake async DB (no Postgres)
# ──────────────────────────────────────────────────────────────
class FakeResult:
    """Mimics a SQLAlchemy Result for the bits our code uses."""
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar

    def scalars(self):
        rows = self._rows
        class _Scalars:
            def all(self_inner):
                return rows
            def first(self_inner):
                return rows[0] if rows else None
        return _Scalars()


class FakeDB:
    """Async DB stub. Pass a list of FakeResult to `results` to script execute()."""
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []

    async def execute(self, *a, **k):
        return self._results.pop(0) if self._results else FakeResult()

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass

    def add(self, obj):
        self.added.append(obj)


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def scripted_db():
    """Factory: scripted_db([rows_for_execute1], [rows_for_execute2], ...) → FakeDB."""
    def _make(*result_rows):
        return FakeDB(results=[FakeResult(rows=r) for r in result_rows])
    return _make


@pytest.fixture
def patch_session_factory(monkeypatch):
    """Patch async_session_factory so code opening its OWN session gets a FakeDB."""
    def _apply(db: FakeDB = None):
        db = db or FakeDB()

        @asynccontextmanager
        async def _factory():
            yield db
        from backend.database import connection
        monkeypatch.setattr(connection, "async_session_factory", _factory)
        return db
    return _apply


# ──────────────────────────────────────────────────────────────
# Bare app + TestClient
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def app():
    """A minimal FastAPI app with the routers and a no-op DB — no heavy lifespan."""
    from backend.routers.auth import router as auth_router
    from backend.routers.dashboard import router as dashboard_router
    from backend.routers.knowledge import router as knowledge_router
    from backend.routers.corrections import router as corrections_router
    from backend.routers.monitoring import router as monitoring_router
    from backend.routers.feedback import router as feedback_router
    from backend.database.connection import get_db

    a = FastAPI()
    for r in (auth_router, dashboard_router, knowledge_router,
              corrections_router, monitoring_router, feedback_router):
        a.include_router(r)

    async def _get_db_override():
        yield FakeDB()
    a.dependency_overrides[get_db] = _get_db_override
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def use_db(app: FastAPI, db: FakeDB):
    """Helper: route get_db to a specific scripted FakeDB for one test."""
    from backend.database.connection import get_db

    async def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    return db


# ──────────────────────────────────────────────────────────────
# Mock LLM
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm(monkeypatch):
    """Replace the graph LLM with a canned async responder."""
    class _Msg:
        def __init__(self, content="Réponse de test.", tool_calls=None):
            self.content = content
            self.type = "ai"
            self.tool_calls = tool_calls or []
            self.usage_metadata = {"input_tokens": 5, "output_tokens": 7}

    class _FakeLLM:
        def __init__(self, content="Réponse de test."):
            self._content = content
        async def ainvoke(self, *a, **k):
            return _Msg(self._content)
        def with_structured_output(self, schema):
            outer = self
            class _Structured:
                async def ainvoke(self_inner, *a, **k):
                    try:
                        return schema()  # empty structured result by default
                    except Exception:
                        return _Msg(outer._content)
            return _Structured()

    fake = _FakeLLM()
    try:
        from backend.domain.graph import llm_factory
        monkeypatch.setattr(llm_factory, "llm", fake, raising=False)
    except Exception:
        pass
    return fake


# ──────────────────────────────────────────────────────────────
# Reset in-memory stores between tests
# ──────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def reset_stores():
    yield
    try:
        from backend.services.rag_service import knowledge_store
        knowledge_store.entries.clear()
        knowledge_store._dirty = True
    except Exception:
        pass
    try:
        from backend.services.session_store import SESSIONS
        SESSIONS.clear()
    except Exception:
        pass
    try:
        from backend.routers.corrections import CORRECTIONS
        CORRECTIONS.clear()
    except Exception:
        pass
