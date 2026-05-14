#!/usr/bin/env bash
# Shared helpers for snapshot/restore/switch scripts.
# Parses DATABASE_URL from backend/.env and exports libpq variables.

set -euo pipefail

# When sourced from a script, ``BASH_SOURCE[0]`` is this file; when sourced
# interactively, fall back to $0.
_lib_self="${BASH_SOURCE[0]:-$0}"
REPO_ROOT="$(cd "$(dirname "${_lib_self}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/backend/.env"
SNAPSHOT_DIR="${REPO_ROOT}/.db-snapshots"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "error: ${ENV_FILE} not found" >&2
  exit 1
fi

# DATABASE_URL format: postgresql[+asyncpg]://user[:pass]@host[:port]/dbname
DATABASE_URL="$(grep -E '^[[:space:]]*DATABASE_URL=' "${ENV_FILE}" | grep -v '^[[:space:]]*#' | head -n1 | cut -d= -f2-)"
# Strip surrounding single/double quotes if the .env value is quoted.
DATABASE_URL="${DATABASE_URL%\"}"
DATABASE_URL="${DATABASE_URL#\"}"
DATABASE_URL="${DATABASE_URL%\'}"
DATABASE_URL="${DATABASE_URL#\'}"
if [[ -z "${DATABASE_URL}" ]]; then
  echo "error: DATABASE_URL missing in ${ENV_FILE}" >&2
  exit 1
fi

# Anchor the driver-tag strip to the scheme so an unlikely ``+asyncpg``
# substring in a password can't get mangled.
PARSE_URL="${DATABASE_URL/postgresql+asyncpg:/postgresql:}"

# Password and port are optional (libpq defaults: empty password, port 5432).
re='^postgresql://([^:@]+)(:([^@]*))?@([^:/]+)(:([0-9]+))?/(.+)$'
if [[ "${PARSE_URL}" =~ $re ]]; then
  export PGUSER="${BASH_REMATCH[1]}"
  export PGPASSWORD="${BASH_REMATCH[3]}"
  export PGHOST="${BASH_REMATCH[4]}"
  export PGPORT="${BASH_REMATCH[6]:-5432}"
  export PGDATABASE="${BASH_REMATCH[7]}"
else
  # Never echo PARSE_URL — it carries the password.
  echo "error: could not parse DATABASE_URL from ${ENV_FILE} (expected postgresql://user[:pass]@host[:port]/db)" >&2
  exit 1
fi

mkdir -p "${SNAPSHOT_DIR}"

snapshot_path_for() {
  local name="$1"
  if [[ -z "${name}" ]]; then
    echo "error: snapshot name required" >&2
    exit 1
  fi
  printf '%s/%s.dump' "${SNAPSHOT_DIR}" "${name}"
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not found on PATH" >&2
    exit 1
  }
}

confirm() {
  local prompt="$1"
  read -r -p "${prompt} [y/N]: " ans
  [[ "${ans}" == "y" || "${ans}" == "Y" ]]
}
