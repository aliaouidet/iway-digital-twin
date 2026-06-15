"""Smoke test: the Claims StateGraph compiles (mirrors the CLAUDE.md smoke)."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")


def test_claims_graph_compiles():
    from backend.domain.graph.builder import build_claims_graph
    graph = build_claims_graph()  # MemorySaver fallback — no Postgres needed
    assert graph is not None
    # Compiled LangGraph exposes astream_events / aget_state used by the executor.
    assert hasattr(graph, "astream_events")
