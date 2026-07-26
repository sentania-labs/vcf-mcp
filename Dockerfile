FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
RUN pip install --upgrade pip hatchling

COPY pyproject.toml .
COPY src/ src/

RUN pip wheel --no-deps --wheel-dir /build/wheels .
RUN pip wheel --wheel-dir /build/wheels mcp starlette uvicorn jinja2 python-multipart cryptography httpx itsdangerous

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

RUN useradd -u 10001 -m -s /bin/bash appuser

WORKDIR /app

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache /wheels/*

# Set up volumes
RUN mkdir -p /data /keys /audit && \
    chown -R appuser:appuser /data /keys /audit
VOLUME ["/data", "/keys", "/audit"]

USER appuser

EXPOSE 8000

# The root filesystem will be read-only in production, so we only write to volumes
CMD ["uvicorn", "vcf_ops_mcp.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
