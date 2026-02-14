# ================================
# STAGE 1 — BUILDER
# ================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends make \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY . .

RUN --mount=type=cache,target=/root/.cache/make \
    make install


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

RUN addgroup --gid $GID $USERGROUP \
    && adduser --uid $UID --gid $GID --disabled-password --gecos "" $USERNAME

WORKDIR $HOME

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends make \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

COPY --from=builder /usr/local/bin /usr/local/bin

COPY --from=builder /app $HOME

RUN chown -R $USERNAME:$USERGROUP $HOME

USER $USERNAME
