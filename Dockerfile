FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN pip install --upgrade pip hatchling

COPY pyproject.toml .
COPY src/ src/

RUN pip wheel --no-deps --wheel-dir /build/wheels .
# mcp is capped below 2.0: the 2.x line removed mcp.server.fastmcp, which
# decision 002 selected as this server's framework. Raising the cap is a
# framework migration, not a version bump.
RUN pip wheel --wheel-dir /build/wheels 'mcp>=1.2.0,<2' starlette uvicorn jinja2 python-multipart cryptography httpx itsdangerous

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

RUN useradd -u 10001 -m -s /bin/bash appuser

WORKDIR /app

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache /wheels/*
COPY --chown=appuser:appuser skills/ /app/skills/

# Set up volumes
RUN mkdir -p /data /keys /audit && \
    chown -R appuser:appuser /data /keys /audit
VOLUME ["/data", "/keys", "/audit"]

USER appuser

EXPOSE 8000

# The root filesystem will be read-only in production, so we only write to volumes.
#
# The entry point is the composition root in vcf_ops_mcp.main, never
# vcf_ops_mcp.app:create_app directly. --factory calls its factory with no
# arguments, so create_app would take its audit_repository default of None
# and /healthz would answer 503 forever. See src/vcf_ops_mcp/main.py.
CMD ["uvicorn", "vcf_ops_mcp.main:create_production_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
