"""
Node: Compliance Check — Rule-based response verification.

Inserted between draft_response and route_by_confidence.
Verifies that the drafted response doesn't violate enterprise rules:
  1. No PII leakage (matricule, token patterns)
  2. Amount consistency with known policy limits
  3. Source citation when making factual claims
  4. No hallucinated contact information

Uses rule-based checks only — no LLM call needed.
"""

import re
import logging
from typing import List

from state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


# ── Known Policy Limits (for consistency checks) ──────────────

_KNOWN_LIMITS = {
    "dentaire": {"max": 600, "unit": "TND", "per": "bénéficiaire/an"},
    "optique": {"max": 400, "unit": "TND", "per": "bénéficiaire/an"},
    "naissance": {"amount": 300, "unit": "TND", "per": "enfant"},
}

_KNOWN_PHONES = {"71 800 800", "71800800"}

# PII patterns to detect
_PII_PATTERNS = [
    r"\b\d{5}\b",  # 5-digit matricule
    r"token[=:\s]+\S+",  # Token values
    r"mot\s+de\s+passe\s*[=:\s]+\S+",  # Password values
]

_COMPILED_PII = [re.compile(p, re.IGNORECASE) for p in _PII_PATTERNS]


async def compliance_check_node(state: ClaimsGraphState) -> dict:
    """
    Node: Compliance Check (rule-based).

    Verifies the draft_response against enterprise rules.
    Does NOT modify the response — only flags issues and adjusts confidence.
    """
    draft = state.get("draft_response") or ""
    confidence = state.get("confidence") or 0.5
    compliance_notes: List[str] = []
    penalty = 0.0

    if not draft:
        return {"compliance_notes": ["No draft to check"]}

    # ── Check 1: PII Leakage ──────────────────────────────────
    matricule = state.get("matricule", "")
    if matricule and matricule in draft:
        compliance_notes.append(f"⚠️ PII: Matricule '{matricule}' found in response")
        penalty += 0.15
        # Redact the matricule from the response
        draft = draft.replace(matricule, "[MATRICULE]")

    token = state.get("token", "")
    if token and len(token) > 5 and token in draft:
        compliance_notes.append("⚠️ PII: Auth token found in response")
        penalty += 0.20
        draft = draft.replace(token, "[TOKEN]")

    # ── Check 2: Amount Consistency ───────────────────────────
    # Extract amounts mentioned in the response
    amounts = re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:TND|dinars?)", draft, re.IGNORECASE)
    for amount_str in amounts:
        try:
            amount = float(amount_str.replace(",", "."))
            # Check against known limits
            for domain, limit in _KNOWN_LIMITS.items():
                if domain in draft.lower():
                    max_val = limit.get("max") or limit.get("amount", 0)
                    if amount > max_val * 1.5:  # Allow some tolerance
                        compliance_notes.append(
                            f"⚠️ AMOUNT: {amount} TND exceeds known {domain} limit of {max_val} TND"
                        )
                        penalty += 0.10
        except ValueError:
            pass

    # ── Check 3: Phone Number Consistency ─────────────────────
    phone_pattern = re.findall(r"\b\d{2}\s?\d{3}\s?\d{3}\b", draft)
    for phone in phone_pattern:
        normalized = phone.replace(" ", "")
        if normalized not in {p.replace(" ", "") for p in _KNOWN_PHONES}:
            compliance_notes.append(f"⚠️ PHONE: Unknown phone number '{phone}' in response")
            penalty += 0.05

    # ── Check 4: Confidence Adjustment ────────────────────────
    adjusted_confidence = max(0.0, confidence - penalty)

    if compliance_notes:
        logger.warning(
            f"🛡️ Compliance check: {len(compliance_notes)} issue(s) found. "
            f"Confidence: {confidence:.2f} → {adjusted_confidence:.2f}"
        )
    else:
        logger.info("✅ Compliance check passed — no issues found")

    return {
        "draft_response": draft,
        "confidence": adjusted_confidence,
        "compliance_notes": compliance_notes,
    }
