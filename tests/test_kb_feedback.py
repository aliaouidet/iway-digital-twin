"""Offline unit tests for the continuous-learning v2 primitives.

Pure functions only (no DB / no Gemini / no embeddings) so they run in the
standard offline suite.
"""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

from backend.config import get_settings
from backend.services.kb_feedback import helpfulness_to_boost
from backend.services.pii_guard import redact_identifiers
from backend.services import rag_service

settings = get_settings()


def test_boost_neutral_matches_static_default():
    # No feedback → exactly the legacy flat boost (backward compatible).
    assert helpfulness_to_boost(0, 0) == settings.HITL_BOOST_FACTOR


def test_boost_orders_by_helpfulness():
    assert helpfulness_to_boost(10, 0) > helpfulness_to_boost(0, 0) > helpfulness_to_boost(0, 10)


def test_boost_clamped_to_max():
    assert helpfulness_to_boost(10_000, 0) <= settings.HITL_BOOST_MAX
    assert helpfulness_to_boost(0, 10_000) >= 1.0


def test_redact_masks_long_ids_but_not_amounts_or_dates():
    out = redact_identifiers("CIN 09876543, police 12012500000011, montant 5000 le 12/06/1985")
    assert "09876543" not in out
    assert "12012500000011" not in out
    assert "5000" in out          # 4-digit amounts untouched
    assert "12/06/1985" in out    # slashed dates untouched


def test_hitl_source_id_is_unique_per_call():
    a = rag_service._new_hitl_source_id("sess")
    b = rag_service._new_hitl_source_id("sess")
    assert a != b
    assert a.startswith("hitl-sess-")


def test_servable_excludes_nonserved_lifecycle_states():
    assert rag_service._is_servable({"status": "active"})
    assert rag_service._is_servable({})  # default = active
    for bad in ("retired", "superseded", "conflict"):
        assert not rag_service._is_servable({"status": bad})
