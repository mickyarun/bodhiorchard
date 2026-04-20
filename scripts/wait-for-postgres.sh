#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar
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
