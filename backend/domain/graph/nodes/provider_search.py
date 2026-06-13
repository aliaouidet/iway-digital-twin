"""
Node: Provider Search — annuaire des prestataires de santé conventionnés.

PUBLIC directory data (the list of tiers-payant providers), NOT personal
records. Deliberately absent from cache_policy._PERSONAL_TOOLS: two users
asking "un cardiologue à Sousse" can safely share a cached answer. The PII
shield will still tokenize provider nom/telephone before an external LLM call
(defense-in-depth) and restore them afterwards — that is expected and harmless.

Filter extraction is deterministic (keyword tables + gouvernorat names), no
LLM call. Real mode refuses to pull the unfiltered ~1 MB provider list — with
no usable filter it asks the user to narrow the search instead.
"""

import logging

from backend.domain.state import ClaimsGraphState
from backend.config import get_settings
from backend.services.iway_soap_client import _fold

logger = logging.getLogger("I-Way-Twin")
settings = get_settings()


# Specialty cue → ERP specialty/secteur label. Keys are accent-folded substrings
# matched against the user message; values feed searchPsWithConvTP filters AND
# the client-side refinement in search_prestataires().
_SPECIALTY_CUES = {
    "cardiolog": "Cardiologie",
    "dentiste": "Dentaire",
    "dentaire": "Dentaire",
    "ophtalmo": "Ophtalmologie",
    "dermato": "Dermatologie",
    "gyneco": "Gynécologie",
    "pediatre": "Pédiatrie",
    "pediatri": "Pédiatrie",
    "generaliste": "Médecine Générale",
    "kine": "Kinésithérapie",
    "radiolog": "Radiologie",
    "imagerie": "Radiologie",
    "orthoped": "Orthopédie",
    "orl": "ORL",
    "psychiatr": "Psychiatrie",
    "neurolog": "Neurologie",
    "urolog": "Urologie",
    "gastro": "Gastro-entérologie",
    "pharmacie": "Pharmacie",
    "laboratoire": "Laboratoire",
    "labo ": "Laboratoire",
    "analyse": "Laboratoire",
    "clinique": "Clinique",
    "opticien": "Optique",
    "optique": "Optique",
}


def extract_provider_filters(message: str, gouvernorats: list[str]) -> dict:
    """Deterministic specialty + gouvernorat extraction from a user message."""
    folded = _fold(message)
    specialite = ""
    for cue, label in _SPECIALTY_CUES.items():
        if _fold(cue) in folded:
            specialite = label
            break
    gouvernorat = ""
    for g in gouvernorats:
        if _fold(g) in folded:
            gouvernorat = g
            break
    return {"specialite": specialite, "gouvernorat": gouvernorat}


def _mock_prestataires(criteres: dict) -> list[dict]:
    """Demo directory rows (mock mode only) — same shape as _map_prestataire."""
    rows = [
        {"nom": "Dr. Leila Haddad", "specialite": "Cardiologie", "secteur": "Médecin",
         "gouvernorat": "Sousse", "ville": "Sousse Ville", "adresse": "12, Av. Habib Bourguiba",
         "telephone": "73 225 410", "conventionne": True},
        {"nom": "Dr. Sami Trabelsi", "specialite": "Cardiologie", "secteur": "Médecin",
         "gouvernorat": "Tunis", "ville": "El Menzah", "adresse": "Rés. Jasmin, Bloc B",
         "telephone": "71 884 230", "conventionne": True},
        {"nom": "Clinique El Amen", "specialite": "", "secteur": "Clinique",
         "gouvernorat": "Tunis", "ville": "La Marsa", "adresse": "Av. de la Plage",
         "telephone": "71 749 000", "conventionne": True},
        {"nom": "Laboratoire Central d'Analyses", "specialite": "", "secteur": "Centre Analyse Médical",
         "gouvernorat": "Sfax", "ville": "Sfax Ville", "adresse": "Rue Mongi Slim",
         "telephone": "74 221 870", "conventionne": True},
        {"nom": "Pharmacie Ben Romdhane", "specialite": "", "secteur": "Pharmacie",
         "gouvernorat": "Sousse", "ville": "Hammam Sousse", "adresse": "Route Touristique",
         "telephone": "73 363 120", "conventionne": True},
    ]
    spec, gouv = _fold(criteres.get("specialite")), _fold(criteres.get("gouvernorat"))
    if spec:
        kept = [r for r in rows if spec in _fold(r["specialite"]) or spec in _fold(r["secteur"])]
        rows = kept or rows
    if gouv:
        kept = [r for r in rows if gouv in _fold(r["gouvernorat"])]
        rows = kept or rows
    return rows[: settings.PROVIDER_SEARCH_MAX_RESULTS]


async def provider_search_node(state: ClaimsGraphState) -> dict:
    """
    Node 2i: Provider Search (annuaire conventionné).

    Real path (IWAY_USE_REAL_API): prestatiareWS.searchPsWithConvTP with
    deterministic filters; degrades honestly on SOAP failure; asks the user to
    narrow the search rather than pulling the whole unfiltered directory.
    """
    from backend.services.referentials import known_gouvernorats

    message = state["messages"][-1].content
    gouvernorats = await known_gouvernorats()
    criteres = extract_provider_filters(message, gouvernorats)
    logger.info(f"Provider search criteres: {criteres}")

    if settings.IWAY_USE_REAL_API:
        if not criteres["specialite"] and not criteres["gouvernorat"]:
            # No usable filter → don't pull ~1 MB of directory; ask to narrow.
            return {"system_records": {
                "prestataires": [],
                "criteres": criteres,
                "precision_requise": (
                    "Précisez une spécialité (ex. cardiologue, dentiste, pharmacie) "
                    "et/ou une ville pour affiner la recherche de prestataires."
                ),
            }}
        try:
            from backend.services import iway_soap_client as soap

            prestataires = await soap.search_prestataires(
                specialite=criteres["specialite"],
                gouvernorat=criteres["gouvernorat"],
                num_police=state.get("num_police", ""),
            )
            logger.info(f"Provider search (real API) ok — {len(prestataires)} result(s)")
            return {"system_records": {
                "prestataires": prestataires,
                "criteres": criteres,
                "nombre_resultats": len(prestataires),
            }}
        except Exception as e:
            logger.warning(f"⚠️ Real provider search failed ({e}); degrading honestly")
            from backend.domain.graph.nodes.lookups import _service_unavailable
            return {"system_records": _service_unavailable("résultats de recherche de prestataires")}

    rows = _mock_prestataires(criteres)
    logger.info(f"Provider search returned {len(rows)} result(s) (mock)")
    return {"system_records": {
        "prestataires": rows,
        "criteres": criteres,
        "nombre_resultats": len(rows),
    }}
