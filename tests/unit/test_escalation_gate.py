"""Unit tests for the formal-complaint filing gate (security invariant #3):
a réclamation is filed only on EXPLICIT filing intent, never anger/status checks."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

import pytest
from backend.domain.graph.nodes.escalation import wants_formal_complaint


@pytest.mark.parametrize("msg", [
    "je veux déposer une réclamation",
    "je souhaite déposer une plainte",
    "comment porter plainte",
    "je voudrais introduire une réclamation",
    "merci d'ouvrir une réclamation",
    "pouvez-vous enregistrer ma reclamation",  # unaccented + possessive
])
def test_explicit_filing_intent_detected(msg):
    assert wants_formal_complaint(msg) is True


@pytest.mark.parametrize("msg", [
    "votre service est nul, je suis vraiment furieux",   # anger only
    "je veux parler à un agent",                          # handoff, not filing
    "où en est ma réclamation ?",                         # status check
    "ma réclamation REC-2026-001 est en cours ?",         # status check
    "",
])
def test_non_filing_intent_not_detected(msg):
    assert wants_formal_complaint(msg) is False
