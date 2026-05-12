#!/bin/sh
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
# Container entrypoint: run pending migrations, then start the API server.

set -e

# Phase D Layer 6: optional egress firewall lockdown. Set
# BODHIORCHARD_EGRESS_FIREWALL=1 in the compose env to enable. Requires
# cap_add: NET_ADMIN on the container. On hosts where iptables isn't
# available (or the cap is denied), the script logs and exits 0 — the
# app-layer Phase B deny list + Phase A workspace pin still apply.
if [ "${BODHIORCHARD_EGRESS_FIREWALL:-0}" = "1" ]; then
    echo "==> Applying egress firewall (Phase D)"
    if [ -x /app/backend/docker/init-firewall.sh ]; then
        /app/backend/docker/init-firewall.sh || true
    elif [ -x /app/docker/init-firewall.sh ]; then
        /app/docker/init-firewall.sh || true
    else
        echo "init-firewall.sh not found; skipping egress lockdown" >&2
    fi
fi

echo "==> Running database migrations"
alembic upgrade head

echo "==> Starting uvicorn"
# Single worker is REQUIRED. A lot of backend state is in-process:
# job_queue._job_store + _running_tasks, event_bus._subscribers, the
# asyncio worker pool itself, and the WS session map all live inside
# one Python process. Adding a second uvicorn worker gives each process
# its own copy of these dicts, so: jobs created on worker A 404 when
# polled on worker B, WS subscribes on A miss publishes from B, cancel
# can't find the task to interrupt, etc. FastAPI + asyncio is already
# concurrent within a single process — --workers >1 is for CPU-bound
# parallelism, which this IO-bound API doesn't need. If we ever need
# horizontal scale, move that state to Redis first.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
