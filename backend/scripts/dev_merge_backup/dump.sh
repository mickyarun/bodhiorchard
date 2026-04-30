#!/usr/bin/env bash
# Dev-only: snapshot the merge-affected tables before testing a merge run.
# Restore with restore.sh <file> if the merge produces bad output.
#
# Connection settings come from env (defaults match local docker compose):
#   PGHOST=localhost PGPORT=5432 PGUSER=test PGPASSWORD=test PGDATABASE=bodhiorchard
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-test}"
PGPASSWORD="${PGPASSWORD:-test}"
PGDATABASE="${PGDATABASE:-bodhiorchard}"
export PGPASSWORD

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${MERGE_BACKUP_DIR:-${SCRIPT_DIR}/backups}"
mkdir -p "${BACKUP_DIR}"

OUT="${BACKUP_DIR}/merge_$(date +%Y%m%d_%H%M%S).sql"

pg_dump \
  --host="${PGHOST}" --port="${PGPORT}" \
  --username="${PGUSER}" --dbname="${PGDATABASE}" \
  --table=synthesized_features \
  --table=knowledge_items \
  --table=knowledge_to_repo \
  --data-only --column-inserts --no-owner --no-privileges \
  > "${OUT}"

echo "Wrote: ${OUT}"
echo "Restore with: $(dirname "${BASH_SOURCE[0]}")/restore.sh ${OUT}"
