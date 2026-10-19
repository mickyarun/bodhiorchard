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

"""The daily who's-out post against real data: content, claiming, posting."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.encryption import encrypt_secret
from app.models.leave_digest_post import DigestStatus
from app.models.leave_request import LeaveKind, LeaveStatus
from app.models.organization import Organization
from app.repositories.leave_digest_post import LeaveDigestPostRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave import digest_scheduler
from app.services.leave.digest_build import build_digest
from app.services.leave.lifecycle import decide, submit
from tests.integration.leave_support import (
    NOBODY,
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration


async def _approved(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, mgr: uuid.UUID, body: LeaveRequestCreate
) -> None:
    async with factory() as db:
        request, _ = await submit(db, org, emp, body)
        if request.status == LeaveStatus.PENDING:
            await decide(
                db,
                org_id=org,
                actor=mgr,
                perms=NOBODY,
                request_id=request.id,
                approve=True,
                note=None,
            )
        await db.commit()


async def _team(factory: Factory) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID, date]:
    org, people, casual = await setup_org(factory, "Asha", "Bala", "Chen", "Mgr")
    for person in people[:3]:
        await report_to(factory, org, person, people[3])
    return org, people, casual, future_monday()


async def test_post_names_who_is_out_and_never_the_type(pg_session_factory: Factory) -> None:
    org, (asha, bala, chen, mgr), casual, mon = await _team(pg_session_factory)
    await _approved(
        pg_session_factory, org, asha, mgr, leave_body(casual, mon, mon + timedelta(2))
    )
    wfh = LeaveRequestCreate(kind=LeaveKind.WFH, start_date=mon, end_date=mon)
    await _approved(pg_session_factory, org, bala, mgr, wfh)
    async with pg_session_factory() as db:
        # Chen's request is still pending: not in the post.
        await submit(db, org, chen, leave_body(casual, mon, mon))
        await db.commit()
        text = await build_digest(db, org, mon)
    assert text is not None
    assert "On leave: Asha (back Thu)" in text
    assert "Working from home: Bala" in text
    assert "Chen" not in text and "Casual" not in text


async def test_no_post_when_nobody_is_working(pg_session_factory: Factory) -> None:
    org, (asha, _b, _c, mgr), casual, mon = await _team(pg_session_factory)
    await _approved(pg_session_factory, org, asha, mgr, leave_body(casual, mon, mon))
    async with pg_session_factory() as db:
        assert await build_digest(db, org, mon - timedelta(days=1)) is None  # Sunday


async def test_a_day_is_claimed_once_and_retried_after_failure(
    pg_session_factory: Factory,
) -> None:
    org, _, _, mon = await _team(pg_session_factory)
    async with pg_session_factory() as db:
        posts = LeaveDigestPostRepository(db, org_id=org)
        assert await posts.claim(mon) is True
        assert await posts.claim(mon) is False
        for _ in range(2):
            await posts.finish(mon, DigestStatus.FAILED, "not_in_channel")
            assert await posts.claim(mon) is True
        await posts.finish(mon, DigestStatus.FAILED, "not_in_channel")
        assert await posts.claim(mon) is False  # three attempts used


async def test_scheduler_posts_once_per_day(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, (asha, _b, _c, mgr), casual, mon = await _team(pg_session_factory)
    await _approved(pg_session_factory, org, asha, mgr, leave_body(casual, mon, mon))
    settings = {"enabled": True, "channel_id": "C0123456", "post_time": "09:30", "timezone": "UTC"}
    async with pg_session_factory() as db:
        organization = await db.get(Organization, org)
        assert organization is not None
        organization.config = {**(organization.config or {}), "leave_digest": settings}
        await db.commit()
    post = AsyncMock(return_value=("C0123456", "1.0", ""))
    monkeypatch.setattr(digest_scheduler, "post_message", post)
    monkeypatch.setattr(digest_scheduler, "AsyncSessionLocal", pg_session_factory)
    token = encrypt_secret("xoxb-test")
    config = {"leave_digest": settings}
    too_early = datetime(mon.year, mon.month, mon.day, 9, 0, tzinfo=UTC)
    on_time = datetime(mon.year, mon.month, mon.day, 9, 45, tzinfo=UTC)
    for now in (too_early, on_time, on_time + timedelta(minutes=1)):
        await digest_scheduler._org_pass(org, token, config, now)
    post.assert_awaited_once()
    channel, text = post.await_args.args[1], post.await_args.args[2]
    assert channel == "C0123456" and "Asha" in text
