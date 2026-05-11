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
