#!/bin/bash
# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
