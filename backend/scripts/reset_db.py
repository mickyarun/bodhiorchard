#!/usr/bin/env python3
"""Truncate all application tables so you can re-run the setup wizard.

Usage (from backend/):
    python -m scripts.reset_db          # uses DATABASE_URL from .env / default
    DATABASE_URL=postgres://... python -m scripts.reset_db

What it does:
    1. TRUNCATE … CASCADE on every application table (respects FKs automatically)
    2. Resets auto-increment sequences via RESTART IDENTITY
    3. Drops orphaned PostgreSQL enum types that block fresh migrations

What happens next:
    - Restart the backend (`uvicorn app.main:app --reload`)
    - The lifespan handler re-seeds RBAC permissions/roles automatically
    - The setup wizard will appear in the frontend as if it's a fresh install
"""

import asyncio
import os
import sys

# ---------------------------------------------------------------------------
# Tables to truncate — order doesn't matter because of CASCADE.
# Alembic's `alembic_version` is intentionally excluded so migrations
# aren't re-applied on next startup.
# ---------------------------------------------------------------------------
TABLES_TO_TRUNCATE = [
    # Auth & identity
    "jwt_tokens",
    "user_email_aliases",
    "org_to_user",
    "users",
    "organizations",
    # BUD documents
    "bud_chat_messages",
    "bud_designs",
    "bud_timeline_events",
    "bud_commits",
    "bud_documents",
    # Knowledge & learning
    "knowledge_to_repo",
    "knowledge_items",
    "feature_learnings",
    "skill_profiles",
    # Repos & scanning
    "tracked_repositories",
    "design_system_refs",
    # Bugs
    "bugs",
    # RBAC (re-seeded on startup)
    "role_permissions",
    "permissions",
    "permission_categories",
    "roles",
    # Notifications & logs
    "notifications",
    "agent_logs",
    # AI & automation
    "agent_skills",
    "agent_skill_bud_stages",
    "bud_agent_tasks",
    "enterprise_rules",
    # Triage & standup
    "triage_sessions",
    "standup_reports",
]

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
        "postgresql+asyncpg://postgres:postgres@localhost:5432/bodhigrove",
    )
    dsn = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn)
    try:
        table_list = ", ".join(TABLES_TO_TRUNCATE)
        sql = f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"
        print(f"Truncating {len(TABLES_TO_TRUNCATE)} tables …")
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
