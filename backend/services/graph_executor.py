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
    "intake": "Classification de votre demande...",
    "rag_retrieval": "Recherche dans la base de connaissances...",
    "claim_extraction": "Analyse des détails de votre réclamation...",
    "action_router": "Identification du service approprié...",
    "dossier_lookup": "Consultation de vos dossiers...",
    "beneficiary_lookup": "Vérification de vos bénéficiaires...",
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
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "matricule": session.get("user_matricule", "12345"),
        "token": session.get("user_token", ""),
        "claim_status": _map_session_to_claim_status(session),
    }

    # Thread ID: matricule + session_id for per-user, per-session isolation
    thread_id = f"{session.get('user_matricule', 'anon')}-{session['id']}"
    config = {"configurable": {"thread_id": thread_id}}

    full_response = ""
    tools_called = []
    active_nodes_seen = set()

    try:
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            kind = event["event"]

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

        # Use the streamed full_response, or fall back to the graph's final message
        if not full_response.strip():
            messages = state_values.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    full_response = last_msg.content

        if full_response.strip():
            return {
                "text": full_response.strip(),
                "confidence": int(confidence * 100) if confidence <= 1.0 else int(confidence),
                "claim_status": claim_status,
                "intent": str(intent) if intent else None,
                "source": "claims_graph",
                "tools_called": graph_tools,
                "degraded": False,
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
