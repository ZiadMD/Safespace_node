# ============================================================
# Safespace Node v2 — Multi-stage Dockerfile
# ============================================================
# Build targets:
#   docker build --target raspi -t safespace-node:raspi .
#   docker build --target gpu   -t safespace-node:gpu .
#   docker build --target headless -t safespace-node:headless .
# ============================================================

# ── Base stage ────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY configs/ configs/
COPY assets/ assets/
COPY src/ src/

# ── Raspberry Pi target ──────────────────────────────────────
FROM base AS raspi

# Install Pi-specific dependencies
COPY requirements-raspi.txt .
RUN pip install --no-cache-dir -r requirements-raspi.txt 2>/dev/null || true

ENV SAFESPACE_DEVICE=raspi
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 docker/healthcheck.py

COPY docker/ docker/
ENTRYPOINT ["python3", "src/main.py"]

# ── GPU target ────────────────────────────────────────────────
FROM base AS gpu

COPY requirements-gpu.txt .
RUN pip install --no-cache-dir -r requirements-gpu.txt 2>/dev/null || true

ENV SAFESPACE_DEVICE=gpu
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 docker/healthcheck.py

COPY docker/ docker/
ENTRYPOINT ["python3", "src/main.py"]

# ── Headless target (no display, CI/testing) ──────────────────
FROM base AS headless

ENV SAFESPACE_NO_DISPLAY=1
ENV SAFESPACE_DEVICE=headless

COPY docker/ docker/
ENTRYPOINT ["python3", "src/main.py", "--no-display"]
