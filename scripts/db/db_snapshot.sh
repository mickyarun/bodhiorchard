#!/usr/bin/env bash
# Snapshot the current Postgres DB to .db-snapshots/<name>.dump (pg_dump -Fc).
# Usage: scripts/db/db_snapshot.sh <name>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

name="${1:-}"
if [[ -z "${name}" ]]; then
  echo "usage: $0 <name>" >&2
  exit 1
fi

require_tool pg_dump
dump_path="$(snapshot_path_for "${name}")"

if [[ -f "${dump_path}" ]]; then
  if ! confirm "Snapshot '${name}' already exists at ${dump_path}. Overwrite?"; then
    echo "aborted"
    exit 0
  fi
fi

echo "Dumping ${PGDATABASE} on ${PGHOST}:${PGPORT} as user '${PGUSER}' -> ${dump_path}"
pg_dump -Fc -f "${dump_path}" "${PGDATABASE}"
echo "Wrote $(du -h "${dump_path}" | cut -f1) snapshot."
