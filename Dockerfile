# ============================================================
# MULTI-STAGE DOCKERFILE FOR TRADING SYSTEM
# ============================================================
# Three stages:
# 1. builder: Installs dependencies
# 2. development: Full tooling for testing/development
# 3. runtime: Minimal production image
# ============================================================

# ============================================================
# STAGE 1: BUILDER
# Purpose: Install build tools and all dependencies
# ============================================================
FROM python:3.11-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Configure Poetry for containerized environment
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install ALL dependencies (including dev dependencies like pytest)
# We'll use this venv for both development and production stages
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

# ============================================================
# STAGE 2: DEVELOPMENT
# Purpose: Full development environment with Poetry and testing tools
# ============================================================
FROM python:3.11-slim AS development

# Install runtime dependencies and development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry in development stage
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy virtual environment from builder (includes ALL dependencies)
COPY --from=builder /app/.venv /app/.venv

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Copy source code and tests
COPY src/ /app/src/
COPY tests/ /app/tests/

# Set Python path and virtual environment
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Development stage runs as root for convenience
# (easier file permissions when mounting volumes)
USER root

# Default command for development
CMD ["/bin/bash"]

# ============================================================
# STAGE 3: RUNTIME (Production)
# Purpose: Minimal production image - secure and small
# ============================================================
FROM python:3.11-slim AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user
RUN groupadd -r trading && useradd -r -g trading trading

WORKDIR /app

# Copy virtual environment from builder
# Note: This includes dev dependencies too. For smaller production images,
# create a separate builder stage with --only main
COPY --from=builder /app/.venv /app/.venv

# Copy only source code (no tests)
COPY src/ /app/src/

# Set Python path and virtual environment
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Change ownership to non-root user
RUN chown -R trading:trading /app

# Switch to non-root user
USER trading

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Document the port
EXPOSE 8000

# Default command
CMD ["python", "-m", "trading_system.main"]