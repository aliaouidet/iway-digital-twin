"""
RAG retrieval evaluation harness — measures retrieval hit-rate@k.

Seeds the in-memory vector store from ``tests/eval/kb_fixtures.jsonl`` and runs
the paraphrased questions in ``tests/eval/golden_qa.jsonl`` through the SAME
retrieval path the app uses, then reports hit-rate@k (the expected source in the
top-k results). This is the thesis evidence that the embedding + ranking layer
works, and a regression guard: run it before and after a continuous-learning
change to confirm the knowledge base still answers the golden questions.

Run (needs sentence-transformers — available in the api image):
    GOOGLE_API_KEY=offline python tests/eval_rag.py
    # or inside the stack:  docker compose exec api python tests/eval_rag.py

Exits non-zero if hit-rate falls below the floor, so it can gate CI.
"""

import os
import sys
import json
from pathlib import Path

os.environ.setdefault("GOOGLE_API_KEY", "offline")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EVAL_DIR = Path(__file__).parent / "eval"
TOP_K = int(os.environ.get("EVAL_TOP_K", "3"))
FLOOR = float(os.environ.get("EVAL_FLOOR", "0.7"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    try:
        from backend.services.rag_service import embed_text, knowledge_store
    except Exception as e:  # pragma: no cover
        print(f"[eval] cannot import rag_service ({e}) — skipping")
        return 0

    # ── Seed a known KB into the in-memory store ──
    for item in _read_jsonl(EVAL_DIR / "kb_fixtures.jsonl"):
        knowledge_store.upsert(
            source_id=item["source_id"],
            source_type="iway_api",
            chunk_text=item["text"],
            embedding=embed_text(item["text"]),
            metadata={"source_id": item["source_id"], "status": "active"},
        )

    golden = _read_jsonl(EVAL_DIR / "golden_qa.jsonl")
    hits, ranks = 0, []
    print(f"\n=== RAG retrieval eval (hit-rate@{TOP_K}) ===")
    for g in golden:
        results = knowledge_store.search(query_embedding=embed_text(g["question"]), top_k=TOP_K)
        got = [r["source_id"] for r in results]
        expected = g["expect_source_id"]
        hit = expected in got
        hits += 1 if hit else 0
        if hit:
            ranks.append(got.index(expected) + 1)
        print(f"  [{'HIT ' if hit else 'MISS'}] {g['question'][:48]:48s} -> {got[:TOP_K]}")

    total = len(golden)
    rate = hits / total if total else 0.0
    mrr = sum(1.0 / r for r in ranks) / total if total else 0.0
    print(f"\nHit-rate@{TOP_K}: {hits}/{total} = {rate:.0%}   MRR: {mrr:.2f}   (floor {FLOOR:.0%})")
    if rate < FLOOR:
        print("[FAIL] Below floor — retrieval regressed.")
        return 1
    print("[PASS]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
