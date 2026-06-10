# ==============================================================================
# STAGE 1: Builder — compiles all Python deps into an isolated venv (/opt/venv)
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build toolchain for C extensions (psycopg / pgvector). Builder-only — not shipped.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Isolated venv so the runtime stage can copy a single self-contained tree.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# --- Layer 1 (STABLE): pip + CPU-only torch ---------------------------------
# torch is large and rarely changes, and is NOT in requirements.txt. Installing it
# in its own layer means editing requirements.txt does NOT re-run this step.
# The pip cache mount keeps wheels between builds (no re-download).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

# --- Layer 2 (VOLATILE): application dependencies ---------------------------
# Copied separately so this is the ONLY layer that re-runs when a dependency
# changes — and thanks to the pip cache mount it only downloads the new wheel
# (e.g. adding `zeep` won't re-fetch the rest).
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# NOTE: the embedding model is intentionally NOT pre-downloaded here. The runtime
# mounts a persistent `hf_cache` volume (see docker-compose.yml), so the model is
# fetched once on first startup and cached across restarts — baking it into the
# image would be discarded by that volume mount and only bloats the build.

# ==============================================================================
# STAGE 2: Runtime — slim image with only the venv + app code
# ==============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime-only system lib for PostgreSQL (no compiler toolchain shipped).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (compose may override to root for the bind-mount dev workflow).
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Pull in the fully-built venv from the builder stage.
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Application code (build context trimmed by .dockerignore).
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
