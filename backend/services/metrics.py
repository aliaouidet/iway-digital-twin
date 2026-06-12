"""
Prometheus metrics — the system's operational counters in one place.

Import-safe by design: if prometheus_client isn't installed (host venv for
offline tests, image before a rebuild), every metric degrades to a no-op so
no caller needs a guard. The /metrics endpoint is exposed in main.py via
prometheus-fastapi-instrumentator (which also provides HTTP latency metrics).

NOTE (multi-worker): with `uvicorn --workers N` each process has its own
registry, so /metrics shows one worker's view per scrape. Acceptable at this
scale; use PROMETHEUS_MULTIPROC_DIR if it ever matters.
"""

try:
    from prometheus_client import Counter, Histogram, Gauge
    METRICS_ENABLED = True
except ImportError:  # pragma: no cover — metrics are optional
    METRICS_ENABLED = False

    class _Noop:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            pass

        def observe(self, *a, **k):
            pass

        def set(self, *a, **k):
            pass

    def Counter(*a, **k):  # noqa: N802 — mirror prometheus_client API
        return _Noop()

    def Histogram(*a, **k):  # noqa: N802
        return _Noop()

    def Gauge(*a, **k):  # noqa: N802
        return _Noop()


# ── Chat pipeline ────────────────────────────────────────────
CACHE_LOOKUPS = Counter(
    "iway_semantic_cache_lookups_total",
    "Semantic cache lookups by result",
    ["result"],  # hit | miss
)

ESCALATIONS = Counter(
    "iway_escalations_total",
    "Human handoffs by trigger path",
    ["path"],  # graph | low_confidence | degraded | manual
)

NODE_DURATION = Histogram(
    "iway_graph_node_duration_seconds",
    "LangGraph node execution time",
    ["node"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

LLM_TOKENS = Counter(
    "iway_llm_tokens_total",
    "LLM tokens consumed by the chat graph",
    ["direction"],  # input | output
)

# ── Infrastructure ───────────────────────────────────────────
PERSIST_FAILURES = Counter(
    "iway_persistence_failures_total",
    "Fire-and-forget DB write failures",
    ["kind"],  # message | escalation | session_create | session_status
)

CIRCUIT_STATE = Gauge(
    "iway_circuit_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["name"],
)
