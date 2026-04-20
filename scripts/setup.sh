#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar
#
# First-run bootstrap for the contributor path.
# Idempotent: safe to re-run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

say() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m[error]\033[0m %s\n" "$*" >&2; exit 1; }

# --- 1. Prereq checks -------------------------------------------------------

say "Checking prerequisites"

command -v docker >/dev/null 2>&1 || fail "docker not found. Install Docker Desktop: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "'docker compose' not available. Upgrade Docker Desktop."
command -v node >/dev/null 2>&1 || fail "node not found. Install Node 18+: https://nodejs.org/"
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install Python 3.12+: https://www.python.org/"

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PY_MAJOR="${PY_VERSION%.*}"
PY_MINOR="${PY_VERSION#*.}"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
  fail "Python 3.12+ required (found $PY_VERSION)"
fi

# --- 2. Env files -----------------------------------------------------------

if [ ! -f backend/.env ]; then
  say "Creating backend/.env from .env.example"
  cp backend/.env.example backend/.env
else
  say "backend/.env already exists — keeping it"
fi

if [ ! -f frontend/.env ]; then
  say "Creating frontend/.env from .env.example"
  cp frontend/.env.example frontend/.env
else
  say "frontend/.env already exists — keeping it"
fi

# --- 3. Python venv + backend install --------------------------------------

if [ ! -d backend/.venv ]; then
  say "Creating Python venv at backend/.venv"
  python3 -m venv backend/.venv
fi

say "Installing backend dependencies (editable + dev extras)"
backend/.venv/bin/pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -e "./backend[dev]"

# --- 4. Infra (postgres + redis) -------------------------------------------

say "Starting infra containers (postgres, redis)"
docker compose -f docker-compose.infra.yml up -d

say "Waiting for postgres to accept connections"
bash scripts/wait-for-postgres.sh

# --- 5. Migrations ----------------------------------------------------------

say "Running database migrations (alembic upgrade head)"
(cd backend && .venv/bin/alembic upgrade head)

# --- 6. Done ----------------------------------------------------------------

cat <<'EOF'

┌─────────────────────────────────────────────────────────────────┐
│  Setup complete.                                                │
│                                                                 │
│  Next:                                                          │
│    npm run dev     # start backend + frontend + multiplayer     │
│                                                                 │
│  Then open:                                                     │
│    http://localhost:3000                                        │
└─────────────────────────────────────────────────────────────────┘

EOF
