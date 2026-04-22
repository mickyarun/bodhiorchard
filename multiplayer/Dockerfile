# syntax=docker/dockerfile:1

# Build context is the repo root so that the sibling `shared/` directory
# referenced by tsconfig (`rootDir: ".."`, `include: ["../shared/race/**/*.ts"]`)
# and by `../../../shared/...` imports is available during `npm run build`.

# ---------- Build stage ----------
FROM node:20-alpine AS builder

WORKDIR /app/multiplayer

COPY multiplayer/package.json multiplayer/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY multiplayer/ ./
COPY shared/ /app/shared/

RUN npm run build

# ---------- Runtime stage ----------
FROM node:20-alpine

WORKDIR /app

COPY multiplayer/package.json multiplayer/package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY --from=builder /app/multiplayer/dist ./dist

EXPOSE 2567
CMD ["node", "dist/multiplayer/src/main.js"]
