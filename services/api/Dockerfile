# ================================
# STAGE 1 — BUILDER
# ================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies for building wheels, if any
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /wheels -r requirements.txt

COPY . .

# ================================
# STAGE 2 — RUNTIME
# ================================
FROM python:3.12-slim AS runtime

# Runtime environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/usr/src/app \
    USERNAME=appuser \
    USERGROUP=appdata \
    UID=9001 \
    GID=9001

# Install minimal runtime OS deps
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && addgroup --gid $GID $USERGROUP \
    && adduser --uid $UID --gid $GID --disabled-password --gecos "" $USERNAME \
    && rm -rf /var/lib/apt/lists/*

WORKDIR $HOME

# Copy only required Python wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*

# Copy application code
COPY --from=builder /app /usr/src/app

RUN chown -R $USERNAME:$USERGROUP $HOME

USER $USERNAME
