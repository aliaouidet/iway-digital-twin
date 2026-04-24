"""
graph.py — Backward compatibility shim.

The real implementation has been decomposed into:
    backend/domain/graph/
    ├── __init__.py        # Re-exports
    ├── builder.py         # build_claims_graph()
    ├── persistence.py     # get_postgres_checkpointer()
    ├── llm_factory.py     # Shared LLM instance
    ├── routing.py         # 4 routing functions
    └── nodes/             # One file per pipeline node

All existing imports continue to work:
    from graph import build_claims_graph
    from graph import get_postgres_checkpointer
"""

from backend.domain.graph.builder import build_claims_graph
from backend.domain.graph.persistence import get_postgres_checkpointer


# Standalone test runner preserved for development
if __name__ == "__main__":
    import asyncio
    import sys
    import logging

    # Force UTF-8 output on Windows consoles
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(message)s",
    )

    async def test_pipeline():
        """Run test queries through all 6 pipeline paths."""
        from langchain_core.messages import HumanMessage

        print("\n" + "=" * 60)
        print("I-Way Claims Graph -- Action Router Test")
        print("=" * 60)

        graph = build_claims_graph()

        # -- Test 1: INFO_QUERY -> RAG -> Draft -> Handoff --
        print(f"\n{'-' * 60}")
        print("[TEST 1] Info query (empty KB -> handoff expected)")
        print("-" * 60)

        r1 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Quel est le plafond dentaire ?")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "active",
            },
            {"configurable": {"thread_id": "test-1"}},
        )
        print(f"  Intent:       {r1.get('intent')}")
        print(f"  Confidence:   {r1.get('confidence')}")
        print(f"  Claim Status: {r1.get('claim_status')}")
        print(f"  Response:     {r1['messages'][-1].content[:200]}...")

        # -- Test 2: CLAIM_ACTION with missing fields -> Clarification --
        print(f"\n{'-' * 60}")
        print("[TEST 2] Claim missing date -> clarification expected")
        print("-" * 60)

        r2 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="J'ai une facture de 350 TND pour une consultation")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "active",
            },
            {"configurable": {"thread_id": "test-2"}},
        )
        print(f"  Intent:       {r2.get('intent')}")
        print(f"  Confidence:   {r2.get('confidence')}")
        print(f"  Claim Status: {r2.get('claim_status')}")
        print(f"  Response:     {r2['messages'][-1].content[:200]}...")

        # -- Test 3: ESCALATION --
        print(f"\n{'-' * 60}")
        print("[TEST 3] Angry user -> escalation expected")
        print("-" * 60)

        r3 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Je veux parler a un humain maintenant")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "active",
            },
            {"configurable": {"thread_id": "test-3"}},
        )
        print(f"  Intent:       {r3.get('intent')}")
        print(f"  Claim Status: {r3.get('claim_status')}")
        print(f"  Response:     {r3['messages'][-1].content[:200]}...")

        # -- Test 4: Stall --
        print(f"\n{'-' * 60}")
        print("[TEST 4] Message while pending_human -> stall expected")
        print("-" * 60)

        r4 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Avez-vous des nouvelles de mon dossier ?")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "pending_human",
            },
            {"configurable": {"thread_id": "test-4"}},
        )
        print(f"  Claim Status: {r4.get('claim_status')}")
        print(f"  Response:     {r4['messages'][-1].content[:200]}...")

        # -- Test 5: PERSONAL_LOOKUP -> Dossier Lookup --
        print(f"\n{'-' * 60}")
        print("[TEST 5] Dossier lookup -> auto-respond with DB data")
        print("-" * 60)

        r5 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Quels sont mes dossiers de remboursement ?")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "active",
            },
            {"configurable": {"thread_id": "test-5"}},
        )
        print(f"  Intent:       {r5.get('intent')}")
        print(f"  Confidence:   {r5.get('confidence')}")
        print(f"  Tools:        {r5.get('tools_called')}")
        print(f"  Sys Records:  {list(r5.get('system_records', {}).keys())}")
        print(f"  Response:     {r5['messages'][-1].content[:250]}...")

        # -- Test 6: PERSONAL_LOOKUP -> Beneficiary Lookup --
        print(f"\n{'-' * 60}")
        print("[TEST 6] Beneficiary lookup -> auto-respond with DB data")
        print("-" * 60)

        r6 = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Qui sont les beneficiaires sur mon contrat ?")],
                "matricule": "12345",
                "token": "test-token",
                "claim_status": "active",
            },
            {"configurable": {"thread_id": "test-6"}},
        )
        print(f"  Intent:       {r6.get('intent')}")
        print(f"  Confidence:   {r6.get('confidence')}")
        print(f"  Tools:        {r6.get('tools_called')}")
        print(f"  Sys Records:  {list(r6.get('system_records', {}).keys())}")
        print(f"  Response:     {r6['messages'][-1].content[:250]}...")

        print(f"\n{'=' * 60}")
        print("All 6 tests complete.")

    asyncio.run(test_pipeline())
