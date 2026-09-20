FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/
# git is needed by the fix flow (sandbox clone and diff)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY scenarios /app/scenarios
ENV PYTHONPATH=/app/backend
