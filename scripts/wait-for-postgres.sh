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

#
# Blocks until the postgres container reports healthy.

set -euo pipefail

TIMEOUT_SECONDS=60
ELAPSED=0
SLEEP_INTERVAL=2

while [ "$ELAPSED" -lt "$TIMEOUT_SECONDS" ]; do
  STATUS="$(docker inspect --format '{{.State.Health.Status}}' bodhiorchard-postgres 2>/dev/null || echo "missing")"
  if [ "$STATUS" = "healthy" ]; then
    printf "\033[1;32m==>\033[0m postgres is healthy\n"
    exit 0
  fi
  sleep "$SLEEP_INTERVAL"
  ELAPSED=$((ELAPSED + SLEEP_INTERVAL))
done

printf "\033[1;31m[error]\033[0m postgres did not become healthy within %ss\n" "$TIMEOUT_SECONDS" >&2
docker logs bodhiorchard-postgres --tail 50 >&2 || true
exit 1
