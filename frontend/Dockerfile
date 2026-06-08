# Build context is the repo root so that Vite's `@shared` alias (resolved to
# `../shared`) and tsconfig's `../shared/**/*.ts` include can locate the
# sibling `shared/` directory during the frontend build.

# ---------- Build stage ----------
FROM node:20-alpine AS builder

WORKDIR /app/frontend

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY frontend/package.json frontend/package-lock.json* ./
# --ignore-scripts is required because `vite-ssg` transitively pulls
# `canvas`, whose `node-pre-gyp install` post-install script tries to
# fetch a pre-built linux-musl binary that doesn't exist (alpine =
# musl, but node-canvas only publishes glibc binaries) and falls back
# to compiling from source — which needs Python + gcc + Cairo headers
# we deliberately don't ship in this image. The frontend build itself
# never invokes canvas (no SSR happens at build time; the browser
# provides the native canvas at runtime), so the package being
# present-without-its-binary is harmless.
RUN npm ci --no-audit --no-fund --ignore-scripts

COPY frontend/ ./
COPY shared/ /app/shared/

# Node's default old-space heap (~1.7 GB) is enough headroom for the
# build today, but the engine chunk now bundles PlayCanvas inline (see
# vite.config.ts — the dedicated playcanvas chunk was removed because
# it caused a cross-chunk module-eval race in production). The larger
# engine chunk pushes Rollup's rendering pass close to the default
# limit; lifting to 4 GB gives comfortable margin and keeps the build
# deterministic across hosts with different system memory.
ENV NODE_OPTIONS="--max-old-space-size=4096"

RUN npx vite build && \
    # Ensure every static asset is world-readable. macOS sometimes hands us
    # 0600 files (e.g. items saved by image tools or copied with cp -p) and
    # Vite preserves those perms — nginx then 403s when serving them.
    find dist -type f -exec chmod a+r {} + && \
    find dist -type d -exec chmod a+rx {} +

# ---------- Runtime stage ----------
FROM nginx:alpine

COPY --from=builder /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
