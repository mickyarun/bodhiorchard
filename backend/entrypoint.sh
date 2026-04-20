#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar
#
# Container entrypoint: run pending migrations, then start the API server.

set -e

echo "==> Running database migrations"
alembic upgrade head

echo "==> Starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
