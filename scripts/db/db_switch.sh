#!/usr/bin/env bash
# Auto-snapshot the current DB (safety) then restore <to>.
# Usage: scripts/db/db_switch.sh <to>
#
# Effect: writes .db-snapshots/auto_<timestamp>.dump first, then drops &
# restores <to>. The auto-snapshot lets you reverse the switch even if you
# forgot to snapshot the current state under a memorable name.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

to="${1:-}"
if [[ -z "${to}" ]]; then
  echo "usage: $0 <to>" >&2
  exit 1
fi

target_path="$(snapshot_path_for "${to}")"
if [[ ! -f "${target_path}" ]]; then
  echo "error: target snapshot not found at ${target_path}" >&2
  echo "create it first with: $(dirname "$0")/db_snapshot.sh ${to}" >&2
  exit 1
fi

ts="$(date +%Y%m%d_%H%M%S)"
auto_name="auto_${ts}"
auto_path="$(snapshot_path_for "${auto_name}")"

if ! confirm "Switch '${PGDATABASE}' on ${PGHOST}:${PGPORT} to snapshot '${to}'? Current state will be saved as '${auto_name}'."; then
  echo "aborted"
  exit 0
fi

echo "[1/2] Safety snapshot -> ${auto_path}"
pg_dump -Fc -f "${auto_path}" "${PGDATABASE}"

echo "[2/2] Restoring '${to}'..."
"${SCRIPT_DIR}/db_restore.sh" "${to}" --yes
echo "Switch complete. Safety snapshot: ${auto_path}"
