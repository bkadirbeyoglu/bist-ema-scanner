# Order Service Dockerfile
# Multi-stage build for production

# Stage 1: Builder
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.7.1
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

WORKDIR /app

COPY pyproject.toml poetry.lock* ./

ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_NO_INTERACTION=1

RUN poetry install --only main --no-root

COPY src/ ./src/

RUN poetry install --only main


# Stage 2: Production
FROM python:3.11-slim as production

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src

ENV PYTHONPATH=/app/src

USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8002/health')" || exit 1

CMD ["uvicorn", "order_service.main:app", "--host", "0.0.0.0", "--port", "8002"]