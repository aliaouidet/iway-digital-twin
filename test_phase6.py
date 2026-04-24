"""Phase 6 verification — sync + retrieval test."""
from backend.workers.sync_worker import sync_knowledge_direct
print("=== Running full knowledge sync ===")
result = sync_knowledge_direct()
print(f"Result: {result}")
print()

print("=== Testing retrieval ===")
from backend.services.rag_service import retrieve_context
queries = [
    "plafond dentaire",
    "delai remboursement",
    "ajouter beneficiaire",
    "urgence etranger",
]
for q in queries:
    results = retrieve_context(q, top_k=2)
    print(f'\nQuery: "{q}"')
    for r in results:
        sim = r["similarity"]
        text_preview = r["chunk_text"][:80].replace("\n", " ")
        print(f"  [{sim:.3f}] {text_preview}...")
print()

print("=== Knowledge stats ===")
from backend.services.rag_service import get_knowledge_stats
stats = get_knowledge_stats()
for k, v in stats.items():
    print(f"  {k}: {v}")
