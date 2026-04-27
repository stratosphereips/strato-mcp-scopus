# Multi-stage build for Scopus MCP Server
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (cached layer, independent of source changes)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Production image
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the entrypoint
ENTRYPOINT ["scopus-mcp"]
