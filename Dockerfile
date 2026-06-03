# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ZTFPASS_CONFIG=/config/config.yaml

WORKDIR /app

# Install the package. Copy only the install inputs first for better layer caching.
# (fastapi/uvicorn/paramiko→cryptography all ship manylinux wheels, so no system
# build toolchain is needed on slim.)
COPY pyproject.toml README.md ./
COPY ztfpass ./ztfpass
RUN pip install .

# Run as a non-root user; config is mounted at /config at runtime (never baked in).
RUN useradd --create-home --uid 1000 ztfpass && mkdir -p /config && chown ztfpass /config
USER ztfpass

EXPOSE 4000

# Liveness: /healthz needs no auth. stdlib only (no curl on slim).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:4000/healthz').status==200 else 1)"

CMD ["ztfpass", "--host", "0.0.0.0", "--port", "4000"]
