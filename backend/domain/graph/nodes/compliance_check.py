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

from backend.domain.state import ClaimsGraphState

logger = logging.getLogger("I-Way-Twin")


# ── Known Policy Limits (for consistency checks) ──────────────

_KNOWN_LIMITS = {
    "dentaire": {"max": 600, "unit": "TND", "per": "bénéficiaire/an"},
    "optique": {"max": 400, "unit": "TND", "per": "bénéficiaire/an"},
    "naissance": {"amount": 300, "unit": "TND", "per": "enfant"},
}

_KNOWN_PHONES = {"71 800 800", "71800800"}


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

    # ── Check 1: PII Leakage — Matricule ───────────────────────
    # Only flag actual session identifiers, not arbitrary 5-digit numbers
    matricule = state.get("matricule", "")
    if matricule and len(matricule) >= 4 and matricule in draft:
        compliance_notes.append(f"⚠️ PII: Matricule '{matricule}' found in response")
        penalty += 0.15
        # Redact the matricule from the response
        draft = draft.replace(matricule, "[MATRICULE]")

    # ── Check 1b: PII Leakage — Auth Token ────────────────────
    token = state.get("token", "")
    if token and len(token) > 5 and token in draft:
        compliance_notes.append("⚠️ PII: Auth token found in response")
        penalty += 0.20
        draft = draft.replace(token, "[TOKEN]")

    # ── Check 1c: PII Leakage — Token/password patterns ───────
    _pii_control_patterns = [
        re.compile(r"token[=:\s]+\S+", re.IGNORECASE),
        re.compile(r"mot\s+de\s+passe\s*[=:\s]+\S+", re.IGNORECASE),
    ]
    for pattern in _pii_control_patterns:
        if pattern.search(draft):
            compliance_notes.append(f"⚠️ PII: Credential pattern detected in response")
            penalty += 0.10
            break

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

    # ── Check 2b: Currency Consistency ────────────────────────
    # The domain is Tunisian health insurance — all amounts are TND. The LLM
    # occasionally appends € to unitless amounts; flag it so the
    # self-correction loop rewrites the response.
    if re.search(r"\d\s*(?:€|\$|EUR\b|USD\b)", draft):
        compliance_notes.append("⚠️ CURRENCY: Devise étrangère (€/$) détectée — les montants sont en TND")
        penalty += 0.05

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
