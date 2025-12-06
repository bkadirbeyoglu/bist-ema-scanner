# ═══════════════════════════════════════════════════════════════════════════════
# MARKET DATA SERVICE DOCKERFILE
# Multi-stage build for production-optimized image
# ═══════════════════════════════════════════════════════════════════════════════

# Stage 1: Builder
# Installs dependencies and builds the package
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME=/opt/poetry
ENV PATH="${POETRY_HOME}/bin:${PATH}"

RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry: no virtualenv (we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies only (not the package itself)
# --no-root: Don't install the project, just dependencies
RUN poetry install --no-root --no-dev

# Copy source code
COPY src/ src/

# Install the package
RUN poetry install --only-root

# ───────────────────────────────────────────────────────────────────────────────
# Stage 2: Production
# Minimal runtime image
# ───────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim as production

# Security: Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/src /app/src

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "market_data_service.main:app", "--host", "0.0.0.0", "--port", "8001"]