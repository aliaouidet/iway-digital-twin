"""
PII Guard — reversible pseudonymization of personal data before external LLM calls.

QR2 requires that personal and medical data never be exposed to external AI
services. With the real I-Way API enabled, lookup nodes put real names, birth
dates, and identifiers into ``system_records``, which draft_response_node
serializes into the LLM prompt. When the LLM is the external Gemini API, that
would ship PHI off-platform.

The shield replaces identifying values with opaque tokens (``[PII_1]``…) before
the prompt is built, and restores the real values in the drafted response after
the LLM returns — so the model formats the data without ever seeing it.

When USE_LOCAL_LLM=true (Ollama, on-premise) the shield is inactive: local
inference is the sanctioned path for data-sensitive deployments.
"""

import logging
from typing import Any, Tuple

from backend.config import get_settings

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()

# Record keys whose string values identify a person. Compared case-insensitively
# with ``-`` normalized to ``_``. Structural fields (ids, montants, statuts) are
# not PII and stay readable so the LLM can reason about them.
_PII_KEYS = {
    "nom", "prenom", "nom_complet", "nomcomplet", "nom_adherent", "nomadherent",
    "nom_fille", "titulaire", "beneficiaire", "adherent", "patient",
    "medecin", "prestataire", "nom_ps", "nomps",
    "date_naissance", "datenaissance",
    "matricule", "num_police", "numpolice", "numero_police",
    "rib", "email", "telephone",
}


def pii_shield_active() -> bool:
    """The shield is needed only when responses are drafted by an EXTERNAL LLM."""
    return not settings.USE_LOCAL_LLM


def pseudonymize_records(records: Any) -> Tuple[Any, dict]:
    """Deep-copy ``records`` with identifying values replaced by [PII_n] tokens.

    Returns (sanitized_records, mapping) where mapping is {token: real_value}.
    Identical values share one token, so cross-references stay coherent for the LLM.
    """
    mapping: dict = {}
    reverse: dict = {}

    def _walk(value, key: str = ""):
        if isinstance(value, dict):
            return {k: _walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(v, key) for v in value]
        if (
            key
            and key.lower().replace("-", "_") in _PII_KEYS
            and value is not None
            and not isinstance(value, (dict, list, bool))
        ):
            # Non-str identifying values (datetime.date, int matricule…) would
            # otherwise slip through and be serialized by json default=str.
            sval = value if isinstance(value, str) else str(value)
            if sval.strip():
                if sval not in reverse:
                    token = f"[PII_{len(mapping) + 1}]"
                    reverse[sval] = token
                    mapping[token] = sval
                return reverse[sval]
        return value

    return _walk(records), mapping


def restore_pii(text: str, mapping: dict) -> str:
    """Substitute the real values back into the LLM's drafted response."""
    if not text or not mapping:
        return text
    for token, real in mapping.items():
        text = text.replace(token, real)
    return text
