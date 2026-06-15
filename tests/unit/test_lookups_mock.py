"""Unit tests for the mock personal-data builders (demo/dev mode shapes).
Also locks the French DD/MM/YYYY birth-date format fix."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

import re
from backend.domain.graph.nodes import lookups

_FR_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def test_mock_beneficiaries_shape_and_french_dates():
    data = lookups._mock_beneficiaries()
    benes = data["beneficiaires"]
    assert data["nombre_beneficiaires"] == len(benes) == 3
    for b in benes:
        assert {"nom", "lien", "date_naissance", "couverture_active"} <= set(b)
        # Birth dates must be French DD/MM/YYYY, not ISO (the prose-format fix).
        assert _FR_DATE.match(b["date_naissance"]), b["date_naissance"]


def test_mock_dossiers_shape():
    data = lookups._mock_dossiers()
    assert data["dossiers"] and data["plafond_annuel"] == 5000.0
    d0 = data["dossiers"][0]
    assert {"id", "type", "status", "montant"} <= set(d0)


def test_service_unavailable_is_honest_not_fabricated():
    rec = lookups._service_unavailable("remboursements")
    assert rec["service_indisponible"] is True
    assert "remboursements" in rec["message"]
    # No fabricated rows masquerading as real data.
    assert "dossiers" not in rec and "beneficiaires" not in rec
