"""
rag_engine.py — FAISS-based RAG engine for I-Sante.

Loads the knowledge base, embeds documents with sentence-transformers,
stores vectors in a FAISS index, and exposes a search() function.

Designed for easy upgrade:
  Level 2 (current): FAISS + sentence-transformers
  Level 3 (future):  add BM25 via EnsembleRetriever
  Level 4 (future):  swap to ChromaDB + PDF loader + reranker
"""

import os
import logging
import numpy as np
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("rag-engine")

# ── Configuration ─────────────────────────────────────────────

MOCK_SERVER_URL = os.getenv("MOCK_SERVER_URL", "http://localhost:8000")


# ── RAG Engine Class ──────────────────────────────────────────

class RAGEngine:
    """
    FAISS-based vector search over the I-Sante knowledge base.

    Usage:
        engine = RAGEngine()
        engine.load()
        results = engine.search("plafond dentaire", k=3)
    """

    def __init__(self):
        self._index = None          # FAISS index
        self._documents = []        # list of document dicts
        self._embedder = None       # SentenceTransformer model
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def doc_count(self) -> int:
        return len(self._documents)

    def load(self, knowledge_base: Optional[list] = None):
        """
        Initialize the vector store.

        Args:
            knowledge_base: list of KB dicts (with 'question', 'reponse', 'cible', 'tags').
                            If None, fetches from the mock server or uses fallback.
        """
        import faiss
        from sentence_transformers import SentenceTransformer

        # 1. Load multilingual embedder (384-dim, optimized for French)
        logger.info("Loading multilingual embedding model (paraphrase-multilingual-MiniLM-L12-v2)...")
        self._embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        # 2. Get knowledge base
        if knowledge_base is None:
            knowledge_base = self._fetch_kb()

        self._documents = knowledge_base
        logger.info(f"Indexing {len(self._documents)} documents...")

        # 3. Build text representations for each document
        texts = []
        for doc in self._documents:
            # Combine question + answer + tags for richer embeddings
            tags_str = ", ".join(doc.get("tags", []))
            text = f"{doc['question']} {doc['reponse']} [tags: {tags_str}]"
            texts.append(text)

        # 4. Compute embeddings
        embeddings = self._embedder.encode(texts, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype="float32")

        # 5. Build FAISS index (inner product on normalized vectors = cosine similarity)
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)

        self._loaded = True
        logger.info(f"RAG engine ready: {self._index.ntotal} vectors indexed (dim={dim})")

    def search(self, query: str, k: int = 3) -> str:
        """
        Search the knowledge base for the most relevant documents.

        Args:
            query: user question in natural language
            k: number of results to return

        Returns:
            Formatted string with top-K results and their similarity scores.
        """
        if not self._loaded:
            return "Erreur: le moteur RAG n'est pas initialise."

        # Embed the query
        query_vec = self._embedder.encode([query], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")

        # Search
        k = min(k, self._index.ntotal)
        scores, indices = self._index.search(query_vec, k)

        # Format results
        results = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), 1):
            if idx < 0:
                continue
            doc = self._documents[idx]
            similarity_pct = round(float(score) * 100, 1)
            results.append(
                f"[Resultat {rank} — pertinence {similarity_pct}%]\n"
                f"Q: {doc['question']}\n"
                f"R: {doc['reponse']}\n"
                f"(Cible: {doc.get('cible', 'N/A')})"
            )

        if not results:
            return "Aucune information trouvee dans la base de connaissances."

        return "\n\n".join(results)

    def _fetch_kb(self) -> list:
        """Load KB from the backend API, falling back to direct import for local dev."""
        # In Docker, main.py is in a separate container — use HTTP API
        try:
            import httpx
            resp = httpx.get(
                f"{MOCK_SERVER_URL}/api/v1/knowledge-base", timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            kb = data.get("items", [])
            logger.info(f"Loaded {len(kb)} KB entries from API ({MOCK_SERVER_URL})")
            return kb
        except Exception as api_err:
            logger.warning(f"API fetch failed ({api_err}), trying direct import...")
        # Fallback: direct import works when running locally alongside main.py
        try:
            from main import MOCK_DB
            kb = MOCK_DB.get("knowledge_base", [])
            logger.info(f"Loaded {len(kb)} KB entries from MOCK_DB (direct import)")
            return kb
        except ImportError:
            logger.error("Could not load knowledge base from API or direct import.")
            return []


# ── Module-level singleton ────────────────────────────────────

_engine = RAGEngine()


def get_engine() -> RAGEngine:
    """Get the RAG engine singleton, initializing it on first call."""
    if not _engine.is_loaded:
        _engine.load()
    return _engine


def search(query: str, k: int = 3) -> str:
    """Convenience function: search the knowledge base."""
    return get_engine().search(query, k=k)


# ── Standalone test ───────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Initializing RAG engine...")
    engine = get_engine()
    print(f"Indexed {engine.doc_count} documents.\n")

    test_queries = [
        "Quel est le plafond pour les soins dentaires ?",
        "Comment obtenir la prime de naissance ?",
        "Delai de remboursement des soins",
        "Comment ajouter mon enfant comme beneficiaire ?",
        "Prise en charge des urgences",
        "Soins optiques lunettes",
    ]

    for q in test_queries:
        print(f"{'='*60}")
        print(f"Query: {q}")
        print(f"{'='*60}")
        print(engine.search(q, k=2))
        print()
