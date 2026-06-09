# ---------- Build stage ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.12-slim

WORKDIR /app

# Runtime system dependencies for Full Docker mode:
#   - libpq5         : PostgreSQL client (asyncpg)
#   - git            : clone/fetch target repos agents will analyze
#   - nodejs (20.x)  : runs the Claude Code CLI
#   - claude-code    : Anthropic's CLI; invoked as a subprocess by the backend
# Code-graph indexing now runs in-process via the Python ``code_indexer``
# module (graphify-based, MIT) — no npm dependency for that step.
# curl/gnupg fetch the NodeSource repo key; removed after use.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 git openssh-client curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code@latest && \
    apt-get purge -y --auto-remove curl gnupg && \
    rm -rf /var/lib/apt/lists/* /root/.npm && \
    groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

COPY --from=builder /install /usr/local

# Pre-bake the embedding model (~90 MB) into the image so the backend
# boots fully offline. fastembed defaults to caching under
# /tmp/fastembed_cache; downloading at build time eliminates two
# failure modes that we hit in prod:
#
#   1. First-request latency. A cold worker that gets a `check_feature_
#      _exists` call has to download ~90 MB from HuggingFace before
#      its first reply. With unauthenticated HF traffic and rate
#      limiting this can take tens of seconds.
#   2. Stalled-download wedging the event loop. fastembed's loader
#      sets up an asyncio.Lock that is released only after the model
#      file lands on disk. If the HF download hangs mid-transfer
#      (which it did on 2026-06-08, leaving the cache dir present but
#      missing model_optimized.onnx), every subsequent embedding call
#      blocks behind that lock forever — observed as a 75 minute
#      backend outage where the process was alive but answered no
#      requests.
#
# Pre-baking at build time means the runtime worker always finds the
# ONNX file on disk and never touches the network for model bytes.
#
# Model defaults to BAAI/bge-small-en-v1.5 (see settings.embedding.model
# in app/config.py). Override with --build-arg EMBEDDING_MODEL=... if
# you've switched the prod default. chown the cache to appuser so the
# runtime user can read it (and write new revisions when the model
# version bumps in a future PR).
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}')" && \
    chown -R appuser:appuser /tmp/fastembed_cache

COPY . .

# Create persistent storage roots for cloned repos and the SSH deploy
# key. These get mounted as named volumes in docker-compose; creating
# them here seeds the initial ownership on first volume creation (Docker
# picks up ownership from the image's existing directory only when the
# path exists at build time).
RUN mkdir -p /data/repos /data/ssh && \
    chmod +x /app/entrypoint.sh && \
    chown -R appuser:appuser /app /data
USER appuser

# Force OpenSSL to skip ARM CPU-capability auto-detection. The OpenSSL bundled
# in the `cryptography` wheel probes /proc/cpuinfo for crypto extensions, but
# under Docker Desktop on Apple Silicon the virtualized CPU reports an
# unidentifiable vendor, so OpenSSL enables an instruction the CPU can't run and
# crashes with SIGILL the first time any crypto path executes (e.g. JWT via
# python-jose during startup). Disabling armcap forces the safe baseline; it is
# ignored on amd64 and only forgoes hardware crypto acceleration on real arm64.
ENV OPENSSL_armcap=0

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
