# ============================================================
# MULTI-STAGE DOCKERFILE FOR TRADING SYSTEM
# ============================================================
# This Dockerfile uses a multi-stage build to create a
# production-ready image that is small, secure, and efficient
# ============================================================

# ============================================================
# STAGE 1: BUILDER
# Purpose: Install build tools and compile dependencies
# This stage will be discarded, keeping final image small
# ============================================================
FROM python:3.11-slim AS builder

# Install system dependencies for building Python packages
# Many Python packages require compilation (C extensions):
# - psycopg2: PostgreSQL adapter (needs libpq-dev)
# - cryptography: Encryption (needs build tools)
# - numpy/pandas: Scientific computing (needs gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
    # ↑ Clean apt cache immediately (same layer = smaller size)

# Install Poetry for dependency management
ENV POETRY_VERSION=1.7.1
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Configure Poetry for containerized environment
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Set working directory
WORKDIR /app

# Copy dependency files first (leverage Docker cache)
# If these files don't change, Docker reuses cached layers
COPY pyproject.toml poetry.lock ./

# Install production dependencies only
# --no-root: Don't install the project package itself yet
# --only main: Skip dev dependencies (pytest, black, etc.)
RUN poetry install --no-root --only main && rm -rf $POETRY_CACHE_DIR

# ============================================================
# STAGE 2: RUNTIME
# Purpose: Minimal production image with just what's needed
# ============================================================
FROM python:3.11-slim AS runtime

# Install only runtime dependencies
# curl: For health checks
# libpq5: PostgreSQL client library (if using psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
# Running as root in production is a security risk
RUN groupadd -r trading && useradd -r -g trading trading

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
# This is the key to multi-stage builds!
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ /app/src/

# Set Python path to find our modules
ENV PYTHONPATH=/app/src

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Python optimizations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# PYTHONUNBUFFERED: Ensures logs appear immediately
# PYTHONDONTWRITEBYTECODE: Don't create .pyc files

# Change ownership to non-root user
RUN chown -R trading:trading /app

# Switch to non-root user
USER trading

# Health check for container orchestrators
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Document the port (informational)
EXPOSE 8000

# Default command
CMD ["python", "-m", "trading_system.main"]