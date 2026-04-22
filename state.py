"""
state.py — LangGraph State Definition for I-Way Claims Management.

This is the single source of truth for all data flowing through the graph.
Every node reads from and writes to this state via partial dict returns.

Design Rules:
  1. Fields with reducers (Annotated) ACCUMULATE across nodes.
  2. Fields without reducers OVERWRITE on each update.
  3. Optional fields default to None — nodes must handle this gracefully.
  4. Security-sensitive fields (token, matricule) are NEVER sent to the LLM.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── Enums ─────────────────────────────────────────────────────

class ClaimIntent(str, Enum):
    """Classified intent from the intake node."""
    INFO_QUERY = "info_query"           # "What's the dental ceiling?"
    CLAIM_ACTION = "claim_action"       # "Submit my reimbursement"
    ESCALATION = "escalation"           # "I want a human" / anger detected
    PERSONAL_LOOKUP = "personal_lookup" # "Show me my dossiers"


class HumanDecision(str, Enum):
    """Decision from the human-in-the-loop review."""
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


# ── Structured Claim Details ──────────────────────────────────

@dataclass
class ClaimDetails:
    """Structured data extracted from user's claim request."""
    procedure_type: Optional[str] = None      # e.g., "soins_dentaires", "optique"
    amount_claimed: Optional[float] = None     # Amount in TND
    date_of_service: Optional[str] = None      # ISO date string
    provider_name: Optional[str] = None        # Doctor/clinic name
    receipt_data: Optional[dict] = None        # OCR-extracted receipt info (Phase 2)

    def missing_required_fields(self) -> list[str]:
        """Return names of required fields that are still None.

        Used by the routing logic to decide between clarification
        (missing data) and handoff (complete data but complex case).
        """
        missing = []
        if not self.procedure_type:
            missing.append("type d'acte médical")
        if self.amount_claimed is None:
            missing.append("montant réclamé")
        if not self.date_of_service:
            missing.append("date de l'acte")
        return missing


# ── Retrieved Document ────────────────────────────────────────

@dataclass
class RetrievedDoc:
    """A single document retrieved from the RAG knowledge base."""
    content: str
    source_id: str
    source_type: str          # "iway_api" | "hitl_validated"
    similarity: float
    metadata: dict = field(default_factory=dict)


# ── Custom Reducers ───────────────────────────────────────────

def merge_claim_details(
    existing: Optional[ClaimDetails],
    update: Optional[ClaimDetails],
) -> Optional[ClaimDetails]:
    """Merge claim details — update overwrites only non-None fields."""
    if existing is None:
        return update
    if update is None:
        return existing
    merged = ClaimDetails(
        procedure_type=update.procedure_type or existing.procedure_type,
        amount_claimed=update.amount_claimed if update.amount_claimed is not None else existing.amount_claimed,
        date_of_service=update.date_of_service or existing.date_of_service,
        provider_name=update.provider_name or existing.provider_name,
        receipt_data=update.receipt_data or existing.receipt_data,
    )
    return merged


def replace_list(existing: list[RetrievedDoc], update: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """Replace retrieved docs entirely on each RAG call (not accumulate)."""
    return update


# ── The Graph State ───────────────────────────────────────────

class ClaimsGraphState(TypedDict):
    """
    The complete state carried through every node in the claims graph.

    Reducer rules:
      - messages:        APPENDS (via add_messages) — full conversation history
      - retrieved_docs:  REPLACES (via replace_list) — latest RAG results only
      - claim_details:   MERGES (via merge_claim_details) — progressive extraction
      - All others:      OVERWRITE — latest value wins
    """

    # ── Conversation ──────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Security (injected, never sent to LLM) ────────────────
    matricule: str
    token: str

    # ── Intent Classification ─────────────────────────────────
    intent: Optional[ClaimIntent]

    # ── RAG Retrieval ─────────────────────────────────────────
    retrieved_docs: Annotated[list[RetrievedDoc], replace_list]
    rag_confidence: Optional[float]    # 0.0 to 1.0

    # ── Claim Processing ──────────────────────────────────────
    claim_details: Annotated[Optional[ClaimDetails], merge_claim_details]

    # ── Claim Lifecycle ───────────────────────────────────────
    #   "active"        — Normal processing, bot is handling the query
    #   "pending_human" — Handed off to human supervisor, bot stalls
    #   "resolved"      — Human has responded, claim is done
    claim_status: Literal["active", "pending_human", "resolved"]

    # ── System Records (from DB tool nodes) ───────────────────
    #   Populated by dossier_lookup_node / beneficiary_lookup_node.
    #   Example: {"dossiers": [...], "beneficiaires": [...]}
    system_records: Optional[dict]

    # ── Response Drafting ─────────────────────────────────────
    draft_response: Optional[str]
    confidence: Optional[float]        # 0.0 to 1.0, overall response confidence
    tools_called: list[str]            # Track which tools were used

    # ── Human-in-the-Loop ─────────────────────────────────────
    human_decision: Optional[HumanDecision]
    human_feedback: Optional[str]      # Agent's correction/edit text
    final_response: Optional[str]      # Post-HITL approved response

    # ── Escalation ────────────────────────────────────────────
    escalation_ticket: Optional[dict]  # {"case_id": ..., "queue_position": ...}
    escalation_reason: Optional[str]
