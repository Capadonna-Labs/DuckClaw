# DuckClaw gateway / db-writer / knowledge-indexer runtime image
# Build: docker build -f docker/gateway/Dockerfile -t duckclaw/gateway:latest .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
COPY integrations/ integrations/
COPY services/api-gateway/ services/api-gateway/
COPY services/db-writer/ services/db-writer/
COPY services/knowledge-indexer/ services/knowledge-indexer/
COPY config/ config/

# mlx is darwin-only and skipped on Linux.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/services /app/services
COPY --from=builder /app/config /app/config
COPY --from=builder /app/integrations /app/integrations
COPY --from=builder /app/pyproject.toml /app/uv.lock /app/README.md /app/
COPY docker/gateway/entrypoint.sh /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DUCKCLAW_REPO_ROOT=/app \
    DUCKCLAW_GATEWAY_DB_PATH=/data/duckclaw.duckdb

RUN mkdir -p /data && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["python", "services/api-gateway/uvicorn_pm2.py", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "services/api-gateway"]
