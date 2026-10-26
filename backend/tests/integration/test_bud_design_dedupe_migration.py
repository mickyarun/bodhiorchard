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

"""Data test for migration ``35ecdf822b3c`` (one design row per bud/repo).

The session-wide test database is migrated to head while empty, so the
duplicate-collapse step never sees data there. This test builds its own
database at the revision before, seeds the duplicates the old upsert race
left behind, and checks what the migration keeps, moves and drops.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.integration.alembic_support import run_alembic

pytestmark = pytest.mark.integration

_BEFORE = "0b77846123b0"
_DEDUPE = "35ecdf822b3c"

ORG = uuid.UUID(int=0xA)
BUD, SOLO_BUD = uuid.UUID(int=0xB1), uuid.UUID(int=0xB2)
# OLD_READY and KEEP have HTML; NEWEST_EMPTY is the most recently updated
# but failed without any, so it must not be the row that survives.
OLD_READY, KEEP, NEWEST_EMPTY, SOLO = (uuid.UUID(int=n) for n in (0xD1, 0xD2, 0xD3, 0xD4))


@pytest_asyncio.fixture
async def scratch_db_url(pg_async_url: str) -> AsyncIterator[str]:
    """A fresh database in the test container, migrated to just before dedupe."""
    name = f"dedupe_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(pg_async_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    scratch_url = make_url(pg_async_url).set(database=name).render_as_string(hide_password=False)
    try:
        ext = create_async_engine(scratch_url, isolation_level="AUTOCOMMIT")
        try:
            async with ext.connect() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        finally:
            await ext.dispose()
        # env.py runs alembic under asyncio.run, which can't nest in this loop.
        await asyncio.to_thread(run_alembic, scratch_url, "upgrade", _BEFORE)
        yield scratch_url
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _seed(conn: AsyncConnection) -> None:
    """Insert three (bud, NULL) duplicates plus their chat rows, and one clean design."""
    await conn.execute(
        text("INSERT INTO organizations (id, name, slug) VALUES (:o, 'Org', :slug)"),
        {"o": ORG, "slug": f"org-{uuid.uuid4().hex[:8]}"},
    )
    await conn.execute(
        text(
            "INSERT INTO bud_documents (id, org_id, bud_number, title, status) VALUES "
            "(:b, :o, 1, 'Dup', 'design'), (:s, :o, 2, 'Solo', 'design')"
        ),
        {"b": BUD, "s": SOLO_BUD, "o": ORG},
    )
    designs = [
        (OLD_READY, BUD, "ready", "<p>old</p>", 3),
        (KEEP, BUD, "ready", "<p>keep</p>", 2),
        (NEWEST_EMPTY, BUD, "failed", None, 1),
        (SOLO, SOLO_BUD, "ready", "<p>solo</p>", 0),
    ]
    for design_id, bud_id, status, html, hours_ago in designs:
        await conn.execute(
            text(
                "INSERT INTO bud_designs "
                "(id, org_id, bud_id, repo_id, status, design_html, updated_at) "
                "VALUES (:id, :o, :b, NULL, :st, :html, now() - CAST(:age AS interval))"
            ),
            {
                "id": design_id,
                "o": ORG,
                "b": bud_id,
                "st": status,
                "html": html,
                "age": timedelta(hours=hours_ago),
            },
        )
    for design_id, message in [(OLD_READY, "from old"), (NEWEST_EMPTY, "from newest")]:
        await conn.execute(
            text(
                "INSERT INTO bud_chat_messages (id, org_id, bud_id, section, role, message, "
                "design_id) VALUES (gen_random_uuid(), :o, :b, 'design', 'user', :m, :d)"
            ),
            {"o": ORG, "b": BUD, "m": message, "d": design_id},
        )
    # 'design': only duplicates have a session, so the most recent one moves.
    # 'other': the kept row already has one, so the duplicate's goes.
    sessions = [
        (OLD_READY, "design", 0x51, 3),
        (NEWEST_EMPTY, "design", 0x52, 1),
        (OLD_READY, "other", 0x53, 0),
        (KEEP, "other", 0x54, 0),
    ]
    for design_id, section, session, hours_ago in sessions:
        await conn.execute(
            text(
                "INSERT INTO bud_section_sessions (id, org_id, bud_id, section, session_id, "
                "message_count, design_id, updated_at) VALUES (gen_random_uuid(), :o, :b, "
                ":sec, :sess, 1, :d, now() - CAST(:age AS interval))"
            ),
            {
                "o": ORG,
                "b": BUD,
                "sec": section,
                "sess": uuid.UUID(int=session),
                "d": design_id,
                "age": timedelta(hours=hours_ago),
            },
        )


@pytest.mark.asyncio
async def test_dedupe_keeps_newest_row_with_html_and_moves_references(
    scratch_db_url: str,
) -> None:
    """Duplicates collapse onto the newest row with HTML; references follow it."""
    engine = create_async_engine(scratch_db_url)
    try:
        async with engine.begin() as conn:
            await _seed(conn)

        await asyncio.to_thread(run_alembic, scratch_db_url, "upgrade", _DEDUPE)

        async with engine.connect() as conn:
            designs = (
                await conn.execute(text("SELECT id, design_html FROM bud_designs ORDER BY bud_id"))
            ).all()
            message_designs = set(
                (await conn.execute(text("SELECT design_id FROM bud_chat_messages"))).scalars()
            )
            sessions = set(
                (
                    await conn.execute(
                        text("SELECT section, session_id, design_id FROM bud_section_sessions")
                    )
                ).tuples()
            )

        assert [tuple(row) for row in designs] == [
            (KEEP, "<p>keep</p>"),
            (SOLO, "<p>solo</p>"),
        ]
        assert message_designs == {KEEP}
        assert sessions == {
            ("design", uuid.UUID(int=0x52), KEEP),
            ("other", uuid.UUID(int=0x54), KEEP),
        }

        async with engine.connect() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO bud_designs (id, org_id, bud_id, status) "
                        "VALUES (gen_random_uuid(), :o, :b, 'pending')"
                    ),
                    {"o": ORG, "b": BUD},
                )
    finally:
        await engine.dispose()
