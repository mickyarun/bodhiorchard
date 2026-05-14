#!/usr/bin/env bash
# Restore Postgres DB from .db-snapshots/<name>.dump.
# Drops the existing DB after confirmation, recreates it, restores, runs alembic upgrade head.
# Usage: scripts/db/db_restore.sh <name> [--yes]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

# Scan all args (not just $2) so `--yes` is recognised regardless of order.
name=""
auto_yes=""
for arg in "$@"; do
  case "${arg}" in
    --yes) auto_yes="--yes" ;;
    -*)    echo "error: unknown flag: ${arg}" >&2; exit 1 ;;
    *)     if [[ -z "${name}" ]]; then name="${arg}"; else echo "error: extra arg: ${arg}" >&2; exit 1; fi ;;
  esac
done
if [[ -z "${name}" ]]; then
  echo "usage: $0 <name> [--yes]" >&2
  exit 1
fi

require_tool pg_restore
require_tool psql

dump_path="$(snapshot_path_for "${name}")"
if [[ ! -f "${dump_path}" ]]; then
  echo "error: snapshot not found at ${dump_path}" >&2
  exit 1
fi

if [[ "${auto_yes}" != "--yes" ]]; then
  if ! confirm "About to DROP and recreate '${PGDATABASE}' on ${PGHOST}:${PGPORT}. Continue?"; then
    echo "aborted"
    exit 0
  fi
fi

echo "Terminating connections to ${PGDATABASE}..."
psql -d postgres -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${PGDATABASE}' AND pid<>pg_backend_pid();" >/dev/null

echo "Dropping ${PGDATABASE}..."
psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"${PGDATABASE}\";" >/dev/null
echo "Creating ${PGDATABASE}..."
# OWNER intentionally matches PGUSER. If a dump was created under a different
# role, ``pg_restore --no-owner`` (below) ignores ownership metadata anyway.
psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${PGDATABASE}\" OWNER \"${PGUSER}\";" >/dev/null

echo "Restoring from ${dump_path}..."
pg_restore --no-owner --no-acl -d "${PGDATABASE}" "${dump_path}"

echo "Running alembic upgrade head..."
(
  cd "${REPO_ROOT}/backend"
  PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/python3129/bin/python}"
  "${PYTHON_BIN}" -m alembic upgrade head
)
echo "Restore complete."
