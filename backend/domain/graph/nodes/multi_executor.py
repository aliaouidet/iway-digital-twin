"""
Node: Multi-Intent Executor — Runs all sub-intents within a single node.

Replaces the broken Send()-based fan-out approach. Instead of creating
independent graph branches (which can't share state), this node directly
calls the appropriate tool functions for each sub-intent and accumulates
all results into a single state dict before passing to draft_response.

Uses asyncio.gather() for concurrent execution when possible, respecting
the 2-3 second latency budget.
"""

import asyncio
import logging

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


async def _execute_personal_lookup(state: ClaimsGraphState) -> dict:
    """Execute a personal_lookup sub-intent (dossier or beneficiary)."""
    from backend.domain.graph.nodes.lookups import (
        dossier_lookup_node,
        beneficiary_lookup_node,
    )

    # Default to dossier lookup — covers "mes dossiers", "remboursements", etc.
    # For the multi-intent case, we skip the LLM-based action_router to save
    # latency and default to dossier (the most common personal_lookup).
    result = await dossier_lookup_node(state)
    logger.info(f"Personal lookup executed: {list(result.get('system_records', {}).keys())}")
    return result


async def _execute_info_query(state: ClaimsGraphState, query: str) -> dict:
    """Execute an info_query sub-intent (RAG retrieval)."""
    from backend.domain.graph.nodes.rag_retrieval import rag_retrieval_node
    from langchain_core.messages import HumanMessage

    # Override the last message with the specific sub-query so RAG
    # searches for the right thing (not the full multi-intent prompt)
    modified_state = dict(state)
    modified_state["messages"] = list(state["messages"][:-1]) + [
        HumanMessage(content=query)
    ]

    result = await rag_retrieval_node(modified_state)
    logger.info(
        f"Info query executed for '{query[:50]}...': "
        f"{len(result.get('retrieved_docs', []))} docs"
    )
    return result


async def _execute_claim_action(state: ClaimsGraphState) -> dict:
    """Execute a claim_action sub-intent."""
    from backend.domain.graph.nodes.claim_extraction import claim_extraction_node

    result = await claim_extraction_node(state)
    logger.info("Claim extraction executed")
    return result


async def multi_executor_node(state: ClaimsGraphState) -> dict:
    """
    Multi-Intent Executor — Runs all sub-intents and merges results.

    For each sub-intent in state['sub_intents'], calls the appropriate
    tool function concurrently via asyncio.gather(). Merges all results
    into a single state update so draft_response_node receives complete
    data from ALL sub-intents.

    Handles:
      - personal_lookup → dossier_lookup (DB records)
      - info_query      → rag_retrieval (knowledge base search)
      - claim_action    → claim_extraction (structured extraction)
      - escalation      → escalation (immediate handoff) — NOT parallelized
      - small_talk      → no tool needed (passthrough)
    """
    sub_intents = state.get("sub_intents", [])

    if len(sub_intents) <= 1:
        # Should not reach here (single-intent takes the fast path),
        # but handle gracefully
        logger.warning("Multi-executor called with ≤1 sub-intents, passing through")
        return {}

    logger.info(f"Multi-executor: processing {len(sub_intents)} sub-intents concurrently")

    # Build concurrent tasks for each sub-intent
    tasks = []
    task_labels = []

    for sub in sub_intents:
        intent = sub.get("intent", "info_query")
        query = sub.get("query", "")

        if intent == "personal_lookup":
            tasks.append(_execute_personal_lookup(state))
            task_labels.append(f"personal_lookup")

        elif intent == "info_query":
            tasks.append(_execute_info_query(state, query))
            task_labels.append(f"info_query: {query[:40]}")

        elif intent == "claim_action":
            tasks.append(_execute_claim_action(state))
            task_labels.append("claim_action")

        elif intent == "escalation":
            # Escalation is special — if ANY sub-intent is escalation,
            # we let it flow through draft_response normally and the
            # escalation node handles it separately via single-intent path
            logger.info("Escalation sub-intent detected, skipping in multi-executor")
            continue

        elif intent == "small_talk":
            # No tool needed for small talk
            continue

    if not tasks:
        logger.warning("No executable sub-intents found")
        return {}

    # Run all tool calls concurrently
    logger.info(f"Launching {len(tasks)} concurrent tasks: {task_labels}")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge all results into a single state update
    merged_system_records = {}
    merged_retrieved_docs = []
    merged_rag_confidence = 0.0
    merged_claim_details = None
    merged_tools_called = []

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Sub-intent task {task_labels[i]} failed: {result}")
            continue

        if not isinstance(result, dict):
            continue

        # Merge system_records (dossier/beneficiary data)
        if "system_records" in result and result["system_records"]:
            merged_system_records.update(result["system_records"])
            merged_tools_called.append("dossier_lookup")

        # Merge retrieved_docs (RAG results)
        if "retrieved_docs" in result and result["retrieved_docs"]:
            merged_retrieved_docs.extend(result["retrieved_docs"])
            if "rag_confidence" in result:
                merged_rag_confidence = max(
                    merged_rag_confidence,
                    result.get("rag_confidence", 0.0),
                )
            merged_tools_called.append("rag_retrieval")

        # Merge claim_details
        if "claim_details" in result and result["claim_details"]:
            merged_claim_details = result["claim_details"]
            merged_tools_called.append("claim_extraction")

    logger.info(
        f"Multi-executor merged: "
        f"records={list(merged_system_records.keys())}, "
        f"docs={len(merged_retrieved_docs)}, "
        f"tools={merged_tools_called}"
    )

    # Build the merged state update
    update = {
        "tools_called": merged_tools_called,
    }

    if merged_system_records:
        update["system_records"] = merged_system_records

    if merged_retrieved_docs:
        update["retrieved_docs"] = merged_retrieved_docs
        update["rag_confidence"] = merged_rag_confidence

    if merged_claim_details:
        update["claim_details"] = merged_claim_details

    return update
