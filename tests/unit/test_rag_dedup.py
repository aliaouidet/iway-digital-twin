"""Unit tests for HITL curation primitives: unique ids, servable filter, and the
dedup/conflict branches of async_add_hitl_with_dedup (DB queried via a stub)."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from backend.services import rag_service
from backend.services.rag_service import _is_servable, _new_hitl_source_id

_Q = "Quelle est la prime de naissance ?"
_A = "La prime de naissance est de 300 TND par enfant."


def test_servable_excludes_lifecycle_states():
    assert _is_servable({"status": "active"})
    assert _is_servable({})  # default = active
    for bad in ("retired", "superseded", "conflict"):
        assert not _is_servable({"status": bad})


def test_unique_source_id_per_call():
    a, b = _new_hitl_source_id("sess"), _new_hitl_source_id("sess")
    assert a != b and a.startswith("hitl-sess-")


async def test_dedup_refresh_skips_insert(patch_session_factory, scripted_db, monkeypatch):
    patch_session_factory(scripted_db([("hitl-existing", _Q, _A)]))
    # Guard: the insert path must NOT run on a refresh.
    async def _boom(*a, **k):
        raise AssertionError("insert must be skipped on refresh")
    monkeypatch.setattr(rag_service, "async_add_hitl_knowledge", _boom)

    res = await rag_service.async_add_hitl_with_dedup(
        session_id="s1", question=_Q, answer=_A,
        agent_matricule="88888", agent_name="Agent")
    assert res["status"] == "refreshed"
    assert res["duplicate_of"] == "hitl-existing"


async def test_dedup_conflict_flags_contradiction(patch_session_factory, scripted_db, monkeypatch):
    patch_session_factory(scripted_db([("hitl-existing", _Q, _A)]))
    captured = {}
    async def _fake_add(session_id, question, answer, agent_matricule, agent_name, **kw):
        captured.update(kw)
        return {"status": "added", "source_id": "hitl-new"}
    monkeypatch.setattr(rag_service, "async_add_hitl_knowledge", _fake_add)

    res = await rag_service.async_add_hitl_with_dedup(
        session_id="s1", question=_Q,
        answer="La prime est de 999 TND, un montant totalement différent.",
        agent_matricule="88888", agent_name="Agent")
    assert res["status"] == "conflict"
    assert res["conflicts_with"] == "hitl-existing"
    assert captured.get("status") == "conflict"
    assert captured.get("conflicts_with") == "hitl-existing"


async def test_no_existing_inserts_normally(patch_session_factory, scripted_db, monkeypatch):
    patch_session_factory(scripted_db([]))  # empty KB
    captured = {}
    async def _fake_add(session_id, question, answer, agent_matricule, agent_name, **kw):
        captured.update(kw)
        return {"status": "added", "source_id": "hitl-new"}
    monkeypatch.setattr(rag_service, "async_add_hitl_knowledge", _fake_add)

    res = await rag_service.async_add_hitl_with_dedup(
        session_id="s1", question=_Q, answer=_A,
        agent_matricule="88888", agent_name="Agent")
    assert res["status"] == "added"
    assert captured.get("status", "active") in ("active",) or captured == {} or captured.get("origin") == "resolve"
