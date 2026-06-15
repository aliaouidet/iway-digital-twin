"""Unit tests for the PII shield (security invariant #2): identifying values are
pseudonymized before an external LLM call and restored afterward."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from backend.services.pii_guard import pseudonymize_records, restore_pii


def test_pseudonymize_hides_identifiers_keeps_structure():
    records = {"beneficiaires": [
        {"nom": "Ahmed Tounsi", "date_naissance": "12/06/1985", "montant": 500, "statut": "actif"},
    ]}
    shielded, mapping = pseudonymize_records(records)
    blob = str(shielded)
    assert "Ahmed Tounsi" not in blob
    assert "12/06/1985" not in blob
    assert "[PII_" in blob
    # Structural / non-identifying fields stay readable for the LLM to reason over.
    assert "500" in blob
    assert "actif" in blob
    assert mapping  # at least one token recorded


def test_restore_pii_round_trips_tokens_back():
    records = {"titulaire": "Nadia Mansour"}
    shielded, mapping = pseudonymize_records(records)
    token = next(iter(mapping))
    restored = restore_pii(f"Le titulaire {token} est couvert.", mapping)
    assert "Nadia Mansour" in restored
    assert token not in restored
