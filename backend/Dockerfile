# syntax=docker/dockerfile:1

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
#   - nodejs (20.x)  : runs the Claude Code CLI and `npx gitnexus …`
#   - claude-code    : Anthropic's CLI; invoked as a subprocess by the backend
# curl/gnupg are needed for the NodeSource repo key and removed after install
# to keep the image small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 git openssh-client curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code@latest && \
    apt-get purge -y --auto-remove curl gnupg && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

COPY --from=builder /install /usr/local

COPY . .

# Create persistent storage roots for cloned repos and the SSH deploy key.
# These get mounted as named volumes in docker-compose; creating them here
# seeds the initial ownership on first volume creation.
RUN mkdir -p /data/repos /data/ssh && \
    chmod +x /app/entrypoint.sh && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
