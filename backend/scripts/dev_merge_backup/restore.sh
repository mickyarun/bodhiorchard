#!/usr/bin/env bash
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

# Dev-only: replay a backup produced by dump.sh. Truncates the three
# merge-affected tables (CASCADE handles the FK from synthesized_features
# to knowledge_items), then loads the dump.
#
# Refuses to run if PGDATABASE looks like a production name. Override the
# guard with FORCE_RESTORE=1 if you really mean it on a custom DB name.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: restore.sh <backup-file>" >&2
  exit 64
fi
BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 66
fi

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-test}"
PGPASSWORD="${PGPASSWORD:-test}"
PGDATABASE="${PGDATABASE:-bodhiorchard}"
export PGPASSWORD

if [[ "${FORCE_RESTORE:-0}" != "1" ]]; then
  case "${PGDATABASE}" in
    *prod*|*production*|*live*)
      echo "Refusing: PGDATABASE='${PGDATABASE}' looks like a production DB." >&2
      echo "Set FORCE_RESTORE=1 to override." >&2
      exit 1
      ;;
  esac
fi

echo "Restoring ${BACKUP_FILE} into ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

psql --host="${PGHOST}" --port="${PGPORT}" \
     --username="${PGUSER}" --dbname="${PGDATABASE}" \
     --set=ON_ERROR_STOP=1 <<'EOF'
TRUNCATE TABLE synthesized_features, knowledge_to_repo, knowledge_items CASCADE;
EOF

psql --host="${PGHOST}" --port="${PGPORT}" \
     --username="${PGUSER}" --dbname="${PGDATABASE}" \
     --set=ON_ERROR_STOP=1 \
     < "${BACKUP_FILE}"

echo "Restore complete."
