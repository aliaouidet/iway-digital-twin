"""
Graph Builder — Constructs and compiles the Claims Management LangGraph.

Architecture: Async Handoff + Action Router + Multi-Intent Decomposition.

Single-intent queries follow the fast path (identical to the original DAG).
Multi-intent queries are decomposed by decompose_node, executed concurrently
inside multi_executor_node (asyncio.gather), and then synthesized by
draft_response_node with all accumulated data.

Usage:
    from backend.domain.graph import build_claims_graph
    graph = build_claims_graph()
    result = await graph.ainvoke(initial_state, config)
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from state import ClaimsGraphState

from backend.domain.graph.nodes import (
    decompose_node,
    rag_retrieval_node,
    claim_extraction_node,
    action_router_node,
    dossier_lookup_node,
    beneficiary_lookup_node,
    draft_response_node,
    clarification_node,
    handoff_node,
    stall_node,
    escalation_node,
    respond_node,
)

from backend.domain.graph.nodes.multi_executor import multi_executor_node

from backend.domain.graph.routing import (
    pre_intake_router,
    route_after_decompose,
    route_action,
    route_by_confidence,
)

logger = logging.getLogger("I-Way-Twin")


def build_claims_graph(checkpointer=None):
    """
    Construct and compile the Claims Management LangGraph.

    Graph topology:
      START → pre_intake_router → decompose (or stall)
      decompose → route_after_decompose:
        - Single intent  → direct to handler node (fast path)
        - Multi intent   → multi_executor (concurrent tool calls)
      multi_executor → draft_response → confidence routing → respond → END

    Args:
        checkpointer: LangGraph checkpointer for state persistence.
                      - None:              Falls back to MemorySaver (dev only)
                      - MemorySaver():     Explicit in-memory (testing)
                      - AsyncPostgresSaver: Production persistence

    Returns:
        A compiled LangGraph application.
    """
    graph = StateGraph(ClaimsGraphState)

    # -- Register Nodes --
    graph.add_node("decompose", decompose_node)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("claim_extraction", claim_extraction_node)
    graph.add_node("action_router", action_router_node)
    graph.add_node("dossier_lookup", dossier_lookup_node)
    graph.add_node("beneficiary_lookup", beneficiary_lookup_node)
    graph.add_node("multi_executor", multi_executor_node)
    graph.add_node("draft_response", draft_response_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("handoff", handoff_node)
    graph.add_node("stall", stall_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("respond", respond_node)

    # -- Wire Edges --

    # START → Pre-Intake Router (checks claim_status)
    graph.add_conditional_edges(
        START,
        pre_intake_router,
        {
            "intake": "decompose",   # renamed: intake → decompose
            "stall": "stall",
        },
    )

    # Stall → Respond
    graph.add_edge("stall", "respond")

    # Decompose → Route (opt-in multi-intent)
    #   Single intent  → direct to handler (fast path, zero overhead)
    #   Multi intent   → multi_executor (concurrent tool calls in one node)
    graph.add_conditional_edges(
        "decompose",
        route_after_decompose,
        {
            "rag_retrieval": "rag_retrieval",
            "claim_extraction": "claim_extraction",
            "escalation": "escalation",
            "action_router": "action_router",
            "draft_response": "draft_response",
            "multi_executor": "multi_executor",
        },
    )

    # Action Router → Route to specific DB tool (2-way branch)
    graph.add_conditional_edges(
        "action_router",
        route_action,
        {
            "dossier_lookup": "dossier_lookup",
            "beneficiary_lookup": "beneficiary_lookup",
        },
    )

    # === Single-intent fast path ===
    # RAG / Extraction / DB Lookups → Draft response
    graph.add_edge("rag_retrieval", "draft_response")
    graph.add_edge("claim_extraction", "draft_response")
    graph.add_edge("dossier_lookup", "draft_response")
    graph.add_edge("beneficiary_lookup", "draft_response")

    # === Multi-intent path ===
    # Multi-executor runs all sub-intents concurrently, then → Draft response
    graph.add_edge("multi_executor", "draft_response")

    # Draft → Route by confidence (3-way branch)
    graph.add_conditional_edges(
        "draft_response",
        route_by_confidence,
        {
            "respond": "respond",
            "clarification": "clarification",
            "handoff": "handoff",
        },
    )

    # Clarification → Respond
    graph.add_edge("clarification", "respond")

    # Handoff → Respond
    graph.add_edge("handoff", "respond")

    # Escalation → Respond
    graph.add_edge("escalation", "respond")

    # Respond → END
    graph.add_edge("respond", END)

    # -- Compile --
    memory = checkpointer or MemorySaver()

    compiled = graph.compile(checkpointer=memory)

    checkpointer_type = type(memory).__name__
    logger.info(f"Claims graph compiled (checkpointer: {checkpointer_type})")
    return compiled
