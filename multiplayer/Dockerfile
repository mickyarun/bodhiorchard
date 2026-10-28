# Build context is the repo root so that the sibling `shared/` directory
# referenced by tsconfig (`rootDir: ".."`, `include: ["../shared/race/**/*.ts"]`)
# and by `../../../shared/...` imports is available during `npm run build`.

# ---------- Build stage ----------
FROM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS builder

WORKDIR /app/multiplayer

COPY multiplayer/package.json multiplayer/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY multiplayer/ ./
COPY shared/ /app/shared/

RUN npm run build

# ---------- Runtime stage ----------
FROM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53

WORKDIR /app

COPY multiplayer/package.json multiplayer/package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY --from=builder /app/multiplayer/dist ./dist

COPY multiplayer/docker-entrypoint.sh ./docker-entrypoint.sh

# The room server handles untrusted client messages: don't run it as root.
USER node

EXPOSE 2567
CMD ["sh", "./docker-entrypoint.sh"]
