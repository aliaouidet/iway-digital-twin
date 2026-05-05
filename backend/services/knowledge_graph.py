"""
Knowledge Graph — GraphRAG overlay for relationship-aware retrieval.

Builds a lightweight knowledge graph from Q&A entries and insurance
concepts. On retrieval, traverses 1-2 hops from matched nodes to
pull related context that pure vector search would miss.

No external dependencies — uses Python dicts and lists.

Usage:
    from backend.services.knowledge_graph import knowledge_graph, get_related_context
    related = get_related_context(query, retrieved_docs)
"""

import logging
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict

logger = logging.getLogger("I-Way-Twin")


class KnowledgeGraph:
    """
    Lightweight knowledge graph for insurance domain relationships.

    Nodes: Q&A entries, insurance concepts (dental, optical, etc.)
    Edges: relates_to, covers, limits, exception_of
    """

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}   # node_id → {label, type, data}
        self.edges: Dict[str, List[Dict]] = defaultdict(list)  # node_id → [{target, relation}]
        self._concept_index: Dict[str, Set[str]] = defaultdict(set)  # keyword → {node_ids}

    def add_node(self, node_id: str, label: str, node_type: str, data: Dict = None):
        """Add a node to the graph."""
        self.nodes[node_id] = {
            "label": label,
            "type": node_type,
            "data": data or {},
        }
        # Index by keywords for fast lookup
        for word in label.lower().split():
            if len(word) > 3:  # Skip short words
                self._concept_index[word].add(node_id)

    def add_edge(self, source: str, target: str, relation: str):
        """Add a directed edge between two nodes."""
        self.edges[source].append({"target": target, "relation": relation})

    def get_neighbors(self, node_id: str, max_hops: int = 1) -> List[Dict[str, Any]]:
        """Get all nodes within N hops of the given node."""
        visited = set()
        result = []
        queue = [(node_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_hops:
                continue
            visited.add(current)

            if current != node_id and current in self.nodes:
                result.append({
                    "node_id": current,
                    "depth": depth,
                    **self.nodes[current],
                })

            for edge in self.edges.get(current, []):
                target = edge["target"]
                if target not in visited:
                    queue.append((target, depth + 1))

        return result

    def find_nodes_by_keywords(self, text: str) -> List[str]:
        """Find graph nodes matching keywords in the text."""
        words = text.lower().split()
        matched_ids: Dict[str, int] = defaultdict(int)

        for word in words:
            if len(word) > 3:
                for node_id in self._concept_index.get(word, set()):
                    matched_ids[node_id] += 1

        # Sort by match count descending
        sorted_ids = sorted(matched_ids.keys(), key=lambda nid: matched_ids[nid], reverse=True)
        return sorted_ids[:5]  # Return top 5 matches

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self.edges.values())


# ── Global Knowledge Graph Instance ──────────────────────────

knowledge_graph = KnowledgeGraph()


# ── Insurance Domain Concepts ─────────────────────────────────
# Pre-defined concept nodes and relationships for the insurance domain

_INSURANCE_CONCEPTS = {
    "soins_dentaires": {
        "label": "Soins Dentaires",
        "related": ["plafond_dentaire", "protheses", "orthodontie"],
        "data": {"category": "coverage", "article": "Article 4"},
    },
    "plafond_dentaire": {
        "label": "Plafond Dentaire (600 TND/an/bénéficiaire)",
        "related": ["soins_dentaires", "beneficiaires"],
        "data": {"amount": 600, "currency": "TND", "per": "bénéficiaire/an"},
    },
    "protheses": {
        "label": "Prothèses Dentaires",
        "related": ["soins_dentaires", "plafond_dentaire"],
        "data": {"category": "coverage"},
    },
    "orthodontie": {
        "label": "Orthodontie (enfants < 16 ans)",
        "related": ["soins_dentaires", "beneficiaires"],
        "data": {"age_limit": 16, "category": "coverage"},
    },
    "soins_optiques": {
        "label": "Soins Optiques",
        "related": ["plafond_optique", "lunettes", "lentilles"],
        "data": {"category": "coverage"},
    },
    "plafond_optique": {
        "label": "Plafond Optique (400 TND/an/bénéficiaire)",
        "related": ["soins_optiques", "beneficiaires"],
        "data": {"amount": 400, "currency": "TND", "per": "bénéficiaire/an"},
    },
    "lunettes": {
        "label": "Lunettes de Vue",
        "related": ["soins_optiques", "plafond_optique"],
        "data": {"category": "coverage"},
    },
    "lentilles": {
        "label": "Lentilles de Contact",
        "related": ["soins_optiques", "plafond_optique"],
        "data": {"category": "coverage"},
    },
    "remboursement": {
        "label": "Processus de Remboursement",
        "related": ["delai_remboursement", "feuille_soins", "documents_requis"],
        "data": {"category": "process"},
    },
    "delai_remboursement": {
        "label": "Délai de Remboursement (48h FSE / 15j papier)",
        "related": ["remboursement", "feuille_soins"],
        "data": {"fse_hours": 48, "paper_days": 15},
    },
    "feuille_soins": {
        "label": "Feuille de Soins Électronique (FSE)",
        "related": ["remboursement", "delai_remboursement"],
        "data": {"category": "document"},
    },
    "documents_requis": {
        "label": "Documents Requis pour Remboursement",
        "related": ["remboursement", "feuille_soins"],
        "data": {"category": "process"},
    },
    "beneficiaires": {
        "label": "Bénéficiaires (ayants droit)",
        "related": ["plafond_dentaire", "plafond_optique"],
        "data": {"category": "entity"},
    },
    "urgence": {
        "label": "Prise en Charge Urgences (100%)",
        "related": ["remboursement", "numero_support"],
        "data": {"coverage_rate": 100, "category": "coverage"},
    },
    "numero_support": {
        "label": "Numéro de Support (71 800 800)",
        "related": ["urgence", "service_client"],
        "data": {"phone": "71 800 800"},
    },
    "service_client": {
        "label": "Service Client I-Way",
        "related": ["numero_support"],
        "data": {"category": "contact"},
    },
    "prime_naissance": {
        "label": "Prime de Naissance (300 TND/enfant)",
        "related": ["beneficiaires", "documents_requis"],
        "data": {"amount": 300, "currency": "TND", "per": "enfant"},
    },
    "hospitalisation": {
        "label": "Hospitalisation",
        "related": ["urgence", "remboursement"],
        "data": {"category": "coverage"},
    },
    "delai_carence": {
        "label": "Délai de Carence",
        "related": ["remboursement", "soins_dentaires", "soins_optiques"],
        "data": {"category": "rule"},
    },
}


def build_insurance_graph():
    """Build the insurance domain knowledge graph from pre-defined concepts."""
    global knowledge_graph

    # Add concept nodes
    for concept_id, concept in _INSURANCE_CONCEPTS.items():
        knowledge_graph.add_node(
            node_id=concept_id,
            label=concept["label"],
            node_type="concept",
            data=concept.get("data", {}),
        )

    # Add edges from relationships
    for concept_id, concept in _INSURANCE_CONCEPTS.items():
        for related_id in concept.get("related", []):
            if related_id in _INSURANCE_CONCEPTS:
                knowledge_graph.add_edge(concept_id, related_id, "relates_to")

    logger.info(
        f"🕸️ Knowledge graph built: {knowledge_graph.node_count} nodes, "
        f"{knowledge_graph.edge_count} edges"
    )


def enrich_graph_from_kb(kb_items: List[Dict[str, Any]]):
    """
    Enrich the knowledge graph with Q&A entries from the knowledge base.

    Links Q&A entries to matching concept nodes based on keyword overlap.
    """
    for item in kb_items:
        node_id = f"qa-{item.get('id', 'unknown')}"
        question = item.get("question", "")
        response = item.get("reponse", "")
        label = question[:100]

        knowledge_graph.add_node(
            node_id=node_id,
            label=label,
            node_type="qa_entry",
            data={"question": question, "reponse": response},
        )

        # Link to matching concepts
        text = f"{question} {response}".lower()
        for concept_id, concept in _INSURANCE_CONCEPTS.items():
            concept_label = concept["label"].lower()
            # Simple keyword matching
            concept_words = [w for w in concept_label.split() if len(w) > 3]
            if any(word in text for word in concept_words):
                knowledge_graph.add_edge(node_id, concept_id, "discusses")
                knowledge_graph.add_edge(concept_id, node_id, "answered_by")

    logger.info(f"🕸️ Knowledge graph enriched with {len(kb_items)} Q&A entries "
                f"(total: {knowledge_graph.node_count} nodes, {knowledge_graph.edge_count} edges)")


def get_related_context(query: str, retrieved_docs: List = None, max_hops: int = 1) -> str:
    """
    Get related context from the knowledge graph for a query.

    1. Find concept nodes matching query keywords
    2. Traverse 1-hop neighbors to get related concepts
    3. Format as a context string for LLM injection

    Args:
        query: User's question
        retrieved_docs: Already-retrieved RAG documents (to find their graph connections)
        max_hops: Maximum graph traversal depth

    Returns:
        Formatted context string with related knowledge graph entries
    """
    if knowledge_graph.node_count == 0:
        return ""

    # Find matching nodes from query keywords
    matched_nodes = knowledge_graph.find_nodes_by_keywords(query)

    if not matched_nodes:
        return ""

    # Get neighbors of matched nodes
    related_items = []
    seen = set()

    for node_id in matched_nodes[:3]:  # Top 3 matched nodes
        neighbors = knowledge_graph.get_neighbors(node_id, max_hops=max_hops)
        for neighbor in neighbors:
            nid = neighbor["node_id"]
            if nid not in seen:
                seen.add(nid)
                related_items.append(neighbor)

    if not related_items:
        return ""

    # Format as context string
    context_parts = []
    for item in related_items[:5]:  # Max 5 related items
        label = item["label"]
        data = item.get("data", {})

        if item["type"] == "qa_entry":
            q = data.get("question", "")
            r = data.get("reponse", "")
            if q and r:
                context_parts.append(f"[Lié] Q: {q}\nR: {r}")
        elif item["type"] == "concept":
            details = []
            if "amount" in data:
                details.append(f"{data['amount']} {data.get('currency', 'TND')}")
            if "phone" in data:
                details.append(f"Tél: {data['phone']}")
            if "coverage_rate" in data:
                details.append(f"Taux: {data['coverage_rate']}%")
            detail_str = f" ({', '.join(details)})" if details else ""
            context_parts.append(f"[Concept lié] {label}{detail_str}")

    return "\n".join(context_parts) if context_parts else ""
