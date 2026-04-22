#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar
#
# Container entrypoint: run pending migrations, then start the API server.

set -e

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
