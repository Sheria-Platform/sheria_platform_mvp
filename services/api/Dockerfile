# services/api/Dockerfile
# Multi-stage build for the Sheria FastAPI service (Ubuntu-based)
# Stage 1: Builder — install dependencies
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install build tools needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer cache)
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime — lean production image
FROM python:3.11-slim-bookworm AS runtime

# Security: run as non-root user
RUN groupadd -r sheria && useradd -r -g sheria sheria

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY services/ /app/services/
COPY libs/ /app/libs/

# Ensure Python can find packages in /app
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Drop to non-root
USER sheria

EXPOSE 8000

# Health check matches docker-compose service healthcheck
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production: Uvicorn with multiple workers
CMD ["uvicorn", "services.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info"]
