"""Integration tests for the dashboard /metrics endpoint incl. the period-over-period
comparison block. DB repos are stubbed; auth is exercised with real tokens."""
import os
os.environ.setdefault("GOOGLE_API_KEY", "offline")

import pytest
from backend.routers import dashboard


@pytest.fixture
def stub_metrics(monkeypatch):
    async def _stats(db, start_date=None, end_date=None):
        # The "previous window" (start before the current one) returns smaller numbers.
        if start_date and start_date < "2026-06-08":
            return {"total_traces": 10, "outcomes": {"RAG_RESOLVED": 5},
                    "avg_confidence": 60, "avg_latency_ms": 9000}
        return {"total_traces": 40,
                "outcomes": {"RAG_RESOLVED": 30, "HUMAN_ESCALATED": 4, "AI_FALLBACK": 5, "ERROR": 1},
                "avg_confidence": 70, "avg_latency_ms": 10000}

    async def _ts(db, days=7, start_date=None, end_date=None):
        return [{"day": "06-14", "rag_confidence": 70, "response_time": 10000,
                 "total_traces": 40, "requests": 40}]

    async def _hourly(db, target_date=None):
        return [{"hour": h, "label": f"{h}h", "count": h} for h in range(24)]

    monkeypatch.setattr(dashboard, "get_audit_stats", _stats)
    monkeypatch.setattr(dashboard, "get_audit_time_series", _ts)
    monkeypatch.setattr(dashboard, "get_hourly_traffic", _hourly)


def test_metrics_requires_auth(client):
    assert client.get("/api/v1/metrics").status_code in (401, 403)


def test_metrics_all_time_has_no_comparison(client, auth_headers, stub_metrics):
    r = client.get("/api/v1/metrics", headers=auth_headers("Admin"))
    assert r.status_code == 200
    d = r.json()
    assert d["total_requests"] == 40
    assert d["rag_resolved"] == 30
    assert d["human_escalated"] == 4
    assert d["comparison"] is None


def test_metrics_date_range_has_comparison(client, auth_headers, stub_metrics):
    r = client.get("/api/v1/metrics?start_date=2026-06-08&end_date=2026-06-14",
                   headers=auth_headers("Admin"))
    assert r.status_code == 200
    comp = r.json()["comparison"]
    assert comp is not None
    assert comp["total_requests"] == 10
    assert comp["window_days"] == 7
