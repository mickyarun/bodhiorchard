# Build context is the repo root so that Vite's `@shared` alias (resolved to
# `../shared`) and tsconfig's `../shared/**/*.ts` include can locate the
# sibling `shared/` directory during the frontend build.

# ---------- Build stage ----------
FROM node:20-alpine AS builder

WORKDIR /app/frontend

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
COPY shared/ /app/shared/

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
