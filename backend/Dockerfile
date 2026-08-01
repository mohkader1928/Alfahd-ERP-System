FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./

EXPOSE 8000

# Production: no dev extras (pytest/ruff), no bind-mounted source (COPY, not
# a volume), no --reload, multiple worker processes for real concurrency.
FROM base AS production
RUN uv pip install --system -e "."
COPY . .
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Dev is the default (last) stage so the existing infra/docker-compose.yml —
# which bind-mounts the source over whatever gets COPYed here and doesn't
# pass --target — keeps working unchanged.
FROM base AS dev
RUN uv pip install --system -e ".[dev]"
COPY . .
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
