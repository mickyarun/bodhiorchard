#!/usr/bin/env python3
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

"""Truncate all application tables so you can re-run the setup wizard.

Usage (from backend/):
    python -m scripts.reset_db          # uses DATABASE_URL from .env / default
    DATABASE_URL=postgres://... python -m scripts.reset_db

What it does:
    1. Discovers every public-schema table from information_schema
    2. TRUNCATE … RESTART IDENTITY CASCADE on all of them in one statement
    3. Optionally drops orphaned PostgreSQL enum types (`--drop-enums`)

What happens next:
    - Restart the backend (`uvicorn app.main:app --reload`)
    - The lifespan handler re-seeds RBAC permissions/roles automatically
    - The setup wizard will appear in the frontend as if it's a fresh install
"""

import asyncio
import os
import sys

# Tables we never touch — Alembic's bookkeeping must persist so migrations
# don't re-apply on next startup.
TABLES_TO_PRESERVE = {"alembic_version"}

# PostgreSQL enum types created by SQLAlchemy that may block re-migration.
ENUM_TYPES_TO_DROP = [
    "budstatus",
    "buddesignstatus",
    "budtimelineeventtype",
    "bugseverity",
    "bugstatus",
    "userrole",
    "repostatus",
    "notificationtype",
    "triagestatus",
    "rolescopetype",
]


async def main() -> None:
    """Connect and truncate all tables."""
    try:
        import asyncpg  # noqa: F811
    except ImportError:
        print("ERROR: asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    # Build connection URL — strip the SQLAlchemy driver prefix if present.
    raw_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/bodhiorchard",
    )
    dsn = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = sorted({r["tablename"] for r in rows} - TABLES_TO_PRESERVE)
        if not tables:
            print("No application tables found — nothing to truncate.")
            return

        # Quote each identifier defensively — pg_tables names are trusted, but
        # quoting protects against any future name with mixed case or keywords.
        table_list = ", ".join(f'"{t}"' for t in tables)
        sql = f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"
        print(f"Truncating {len(tables)} tables …")
        await conn.execute(sql)
        print("All tables truncated.")

        # Optionally drop enum types so Alembic doesn't choke on "type already exists".
        drop_enums = "--drop-enums" in sys.argv
        if drop_enums:
            print("Dropping PostgreSQL enum types …")
            for enum_name in ENUM_TYPES_TO_DROP:
                await conn.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
            print(f"Dropped {len(ENUM_TYPES_TO_DROP)} enum types.")

        print("\nDone! Restart the backend to re-seed RBAC permissions.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
