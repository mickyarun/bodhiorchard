#!/bin/bash
# deploy.sh — pull latest code and redeploy on the VPS.
# Usage: ./deploy.sh

set -e

ENV_FILE=".env.production"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found."
  echo "  cp .env.production.example .env.production && nano .env.production"
  exit 1
fi

echo "==> Pulling latest code"
git pull

echo "==> Building images"
docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" build

echo "==> Starting services"
docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" up -d

echo ""
echo "==> Done. Useful commands:"
echo "    Status : docker compose -f docker-compose.prod.yml ps"
echo "    Logs   : docker compose -f docker-compose.prod.yml logs -f"
echo "    Backend: docker compose -f docker-compose.prod.yml logs -f backend"
