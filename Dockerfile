# ==============================================================================
# STAGE 1: Builder
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required for compilation (e.g., C extensions for pgvector/psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies into the venv
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# ==============================================================================
# STAGE 2: Runtime
# ==============================================================================
FROM python:3.11-slim AS runtime

# Set environment variables for the runtime stage
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install minimal runtime system dependencies (libpq5 for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security best practices
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy the compiled virtual environment from the builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy the application code
COPY --chown=appuser:appuser . .

# Switch to the non-root user
USER appuser

# Expose port
EXPOSE 8000

# Default command: run FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
