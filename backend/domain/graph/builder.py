"""
Graph Builder — Constructs and compiles the Claims Management LangGraph.

Architecture: Async Handoff + Action Router (no interrupt_before).
The graph never freezes — low-confidence responses are handled via
clarification loops or async human handoff with stall engagement.

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
    intake_node,
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

from backend.domain.graph.routing import (
    pre_intake_router,
    route_by_intent,
    route_action,
    route_by_confidence,
)

logger = logging.getLogger("I-Way-Twin")


def build_claims_graph(checkpointer=None):
    """
    Construct and compile the Claims Management LangGraph.

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
    graph.add_node("intake", intake_node)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("claim_extraction", claim_extraction_node)
    graph.add_node("action_router", action_router_node)
    graph.add_node("dossier_lookup", dossier_lookup_node)
    graph.add_node("beneficiary_lookup", beneficiary_lookup_node)
    graph.add_node("draft_response", draft_response_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("handoff", handoff_node)
    graph.add_node("stall", stall_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("respond", respond_node)

    # -- Wire Edges --

    # START -> Pre-Intake Router (checks claim_status)
    graph.add_conditional_edges(
        START,
        pre_intake_router,
        {
            "intake": "intake",
            "stall": "stall",
        },
    )

    # Stall -> Respond
    graph.add_edge("stall", "respond")

    # Intake -> Route by intent (4-way branch)
    graph.add_conditional_edges(
        "intake",
        route_by_intent,
        {
            "rag_retrieval": "rag_retrieval",
            "claim_extraction": "claim_extraction",
            "escalation": "escalation",
            "action_router": "action_router",
        },
    )

    # Action Router -> Route to specific DB tool (2-way branch)
    graph.add_conditional_edges(
        "action_router",
        route_action,
        {
            "dossier_lookup": "dossier_lookup",
            "beneficiary_lookup": "beneficiary_lookup",
        },
    )

    # RAG / Extraction / DB Lookups -> Draft response
    graph.add_edge("rag_retrieval", "draft_response")
    graph.add_edge("claim_extraction", "draft_response")
    graph.add_edge("dossier_lookup", "draft_response")
    graph.add_edge("beneficiary_lookup", "draft_response")

    # Draft -> Route by confidence (3-way branch)
    graph.add_conditional_edges(
        "draft_response",
        route_by_confidence,
        {
            "respond": "respond",
            "clarification": "clarification",
            "handoff": "handoff",
        },
    )

    # Clarification -> Respond
    graph.add_edge("clarification", "respond")

    # Handoff -> Respond
    graph.add_edge("handoff", "respond")

    # Escalation -> Respond
    graph.add_edge("escalation", "respond")

    # Respond -> END
    graph.add_edge("respond", END)

    # -- Compile --
    memory = checkpointer or MemorySaver()

    compiled = graph.compile(checkpointer=memory)

    checkpointer_type = type(memory).__name__
    logger.info(f"Claims graph compiled (checkpointer: {checkpointer_type})")
    return compiled
