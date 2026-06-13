"""
Graph Executor — Claims StateGraph execution with token streaming.

Handles:
  - Graph initialization (lazy-load with MemorySaver fallback)
  - Production PostgresSaver initialization
  - Token streaming via astream_events v2
  - Node activity "thinking" indicators

Extracted from chat_service.py to follow SRP (system-design skill).
"""

import logging
import asyncio

from fastapi import WebSocket

from backend.config import get_settings
from backend.services.resilience import llm_circuit

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


# ==============================================================
# CLAIMS GRAPH (initialized once, reused across all sessions)
# ==============================================================

_claims_graph = None
_graph_available = False


def _get_graph():
    """Lazy-load the compiled Claims StateGraph. Returns None if unavailable.

    Uses MemorySaver by default (dev). For production PostgresSaver,
    call init_claims_graph_async() during app lifespan startup.
    """
    global _claims_graph, _graph_available
    if _claims_graph is not None:
        return _claims_graph
    if not _graph_available and _claims_graph is None:
        try:
            from graph import build_claims_graph
            _claims_graph = build_claims_graph()  # MemorySaver fallback
            _graph_available = True
            logger.info("Claims graph loaded (MemorySaver — dev mode)")
        except Exception as e:
            _graph_available = False
            logger.warning(f"Claims graph unavailable (falling back to RAG-only): {e}")
    return _claims_graph


async def init_claims_graph_async():
    """Initialize the Claims Graph with PostgresSaver (production).

    Call this from your FastAPI lifespan handler:
        async with lifespan(app):
            await init_claims_graph_async()
    """
    global _claims_graph, _graph_available
    try:
        from graph import build_claims_graph, get_postgres_checkpointer
        checkpointer = await get_postgres_checkpointer()
        _claims_graph = build_claims_graph(checkpointer=checkpointer)
        _graph_available = True
        logger.info("Claims graph loaded (PostgresSaver — production)")
    except Exception as e:
        logger.warning(f"PostgresSaver init failed, falling back to MemorySaver: {e}")
        _get_graph()  # Fallback to MemorySaver


# ==============================================================
# GRAPH EXECUTION — Token streaming via astream_events
# ==============================================================

# Nodes whose LLM tokens should be streamed to the user in real-time.
_STREAMABLE_NODES = {"draft_response", "stall"}

# Node activity labels shown to the user as "thinking" indicators.
_NODE_LABELS = {
    "decompose": "Décomposition de votre demande...",
    "intake": "Classification de votre demande...",
    "rag_retrieval": "Recherche dans la base de connaissances...",
    "claim_extraction": "Analyse des détails de votre réclamation...",
    "action_router": "Identification du service approprié...",
    "multi_executor": "Traitement de vos demandes...",
    "dossier_lookup": "Consultation de vos dossiers...",
    "beneficiary_lookup": "Vérification de vos bénéficiaires...",
    "reclamation_lookup": "Consultation de vos réclamations...",
    "dossier_detail_lookup": "Recherche du détail de votre dossier...",
    "plafond_lookup": "Consultation de vos plafonds et consommation...",
    "facture_lookup": "Consultation de vos factures...",
    "provider_search": "Recherche de prestataires conventionnés...",
    "draft_response": "Rédaction de la réponse...",
    "clarification": "Vérification des informations...",
    "handoff": "Transfert vers un superviseur...",
    "escalation": "Transfert vers un agent humain...",
}


async def execute_claims_graph(
    query: str,
    session: dict,
    websocket: WebSocket,
) -> dict | None:
    """
    Execute the 12-node Claims StateGraph with real-time token streaming.

    Streams tokens from draft_response_node and stall_node via WebSocket.
    After the graph completes, inspects the final state to determine
    the outcome (auto-respond, clarification, handoff, escalation).

    Returns:
        A result dict with text, confidence, claim_status, tools_called,
        or None if the graph failed.
    """
    from langchain_core.messages import HumanMessage

    graph = _get_graph()
    if graph is None:
        return None  # Signal caller to use RAG fallback

    # -- Construct initial state --
    # NOTE: matricule deliberately defaults to "" (not a demo persona). With real
    # ERP writes wired, a missing matricule must never attribute records to a
    # real-looking user — empty matricule disables writes and personal lookups.
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "matricule": session.get("user_matricule", ""),
        "token": session.get("user_token", ""),
        "num_police": session.get("user_num_police", ""),
        "role": session.get("user_role", ""),
        "id_tiers": session.get("user_id_tiers", ""),
        "claim_status": _map_session_to_claim_status(session),
    }

    # Thread ID: matricule + session_id for per-user, per-session isolation
    thread_id = f"{session.get('user_matricule', 'anon')}-{session['id']}"
    config = {"configurable": {"thread_id": thread_id}}

    import time
    full_response = ""
    tools_called = []
    active_nodes_seen = set()
    node_timings = {}  # {langgraph_node: {start, end}}
    tokens_in = 0
    tokens_out = 0

    try:
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            kind = event["event"]
            metadata = event.get("metadata") or {}
            langgraph_node = metadata.get("langgraph_node")

            # -- Track Sub-Spans for Nodes (Filtered & Consolidated) --
            if langgraph_node and langgraph_node not in ("__start__", "__end__"):
                if kind == "on_chain_start":
                    if langgraph_node not in node_timings:
                        node_timings[langgraph_node] = {"start": time.perf_counter(), "end": None}
                elif kind == "on_chain_end":
                    if langgraph_node in node_timings:
                        node_timings[langgraph_node]["end"] = time.perf_counter()

            # -- Real LLM token usage (every model call in the graph) --
            # LangChain normalizes provider usage into AIMessage.usage_metadata;
            # before this, tokens_used in the audit log was always 0/fake.
            if kind == "on_chat_model_end":
                _out = (event.get("data") or {}).get("output")
                _usage = getattr(_out, "usage_metadata", None)
                if isinstance(_usage, dict):
                    tokens_in += _usage.get("input_tokens", 0) or 0
                    tokens_out += _usage.get("output_tokens", 0) or 0

            # -- Stream LLM tokens from user-facing nodes --
            if kind == "on_chat_model_stream":
                tags = event.get("tags", [])
                parent_node = _extract_node_from_tags(tags)

                if parent_node in _STREAMABLE_NODES:
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        if not (hasattr(chunk, "tool_calls") and chunk.tool_calls):
                            full_response += chunk.content
                            await websocket.send_json({
                                "type": "ai_token",
                                "token": chunk.content,
                            })

            # -- Show "thinking" indicators when nodes start --
            elif kind == "on_chain_start":
                node_name = event.get("name", "")
                if node_name in _NODE_LABELS and node_name not in active_nodes_seen:
                    active_nodes_seen.add(node_name)
                    await websocket.send_json({
                        "type": "thinking",
                        "status": _NODE_LABELS[node_name],
                        "node": node_name,
                    })

        # -- Extract final state after graph completes --
        final_state = await graph.aget_state(config)
        state_values = final_state.values if final_state else {}

        confidence = state_values.get("confidence", 0) or 0
        claim_status = state_values.get("claim_status", "active")
        intent = state_values.get("intent")
        graph_tools = state_values.get("tools_called", [])

        # Process consolidated node timings into sub_spans (+ Prometheus histogram)
        from backend.services.metrics import NODE_DURATION, LLM_TOKENS
        sub_spans = []
        for name, timing in node_timings.items():
            if timing["end"] is not None:
                duration_ms = (timing["end"] - timing["start"]) * 1000
                NODE_DURATION.labels(node=name).observe(duration_ms / 1000.0)

                # If this was the multi_executor, rename it to show the actual tools running
                if name == "multi_executor" and graph_tools:
                    name = f"tool_execution [{', '.join(graph_tools)}]"

                sub_spans.append({"name": name, "duration_ms": round(duration_ms, 1)})

        if tokens_in:
            LLM_TOKENS.labels(direction="input").inc(tokens_in)
        if tokens_out:
            LLM_TOKENS.labels(direction="output").inc(tokens_out)

        # Prefer the graph's CANONICAL final text (respond_node's AIMessage) over
        # the raw streamed chunks. The canonical text is PII-restored and
        # compliance-redacted; raw streamed chunks may still contain [PII_n]
        # placeholders (or the CONFIDENCE: line) when the structured-output
        # fallback path streamed plain text. The UI's final bubble uses the
        # `ai_done.text` built from this return value, so the corrected text
        # replaces whatever was streamed live.
        canonical = ""
        messages = state_values.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if getattr(last_msg, "type", "") == "ai" and getattr(last_msg, "content", ""):
                canonical = last_msg.content
        if canonical.strip():
            full_response = canonical

        if full_response.strip():
            return {
                "text": full_response.strip(),
                "confidence": int(confidence * 100) if confidence <= 1.0 else int(confidence),
                "claim_status": claim_status,
                "intent": str(intent) if intent else None,
                "source": "claims_graph",
                "tools_called": graph_tools,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_used": tokens_in + tokens_out,
                # Structured records from personal lookups (already PII-normalized
                # shapes from lookups.py) — the UI renders these as claim cards.
                "records": state_values.get("system_records") or None,
                "degraded": False,
                "retrieved_docs": [
                    {"content": d.content, "source_id": d.source_id, "similarity": d.similarity}
                    for d in state_values.get("retrieved_docs", [])
                ],
                "graph_context": state_values.get("graph_context", ""),
                "sub_spans": sub_spans,
            }
        else:
            return None  # Empty response — fall back

    except Exception as e:
        logger.error(f"Claims graph execution failed: {e}")
        llm_circuit.record_failure()
        return None  # Signal fallback


def _map_session_to_claim_status(session: dict) -> str:
    """Map the existing session['status'] to the graph's claim_status."""
    status = session.get("status", "active")
    if status == "handoff_pending":
        return "pending_human"
    elif status == "resolved":
        return "resolved"
    else:
        return "active"


def _extract_node_from_tags(tags: list) -> str | None:
    """Extract the graph node name from astream_events tags."""
    for tag in tags:
        if tag in _STREAMABLE_NODES:
            return tag
        for node in _STREAMABLE_NODES:
            if node in tag:
                return node
    return None
