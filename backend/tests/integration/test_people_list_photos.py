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

"""People lists carry each person's stored ``avatar_url`` from Postgres.

Covers the queries that changed to select the photo: the name-and-photo
lookups, the leave calendar and request views (dashboard time off, out
soon, the approval queue), a repo's top contributors and a BUD's commit
contributors.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.api.v1.bud import get_dev_activity
from app.models.bud import BUDDocument
from app.models.dev_activity import DevActivityLog
from app.models.tracked_repository import TrackedRepository
from app.models.user import User
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.user import PersonCard, UserRepository
from app.services.leave.calendar_view import calendar_view
from app.services.leave.lifecycle import decide, submit
from app.services.leave.views import request_reads
from tests.integration.leave_support import (
    NOBODY,
    Factory,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration

PHOTO = "/api/v1/employees/avatars/0123456789abcdef0123456789abcdef"


async def _set_photo(factory: Factory, user_id: uuid.UUID, slack_id: str | None = None) -> None:
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.avatar_url = PHOTO
        user.slack_id = slack_id
        await db.commit()


async def test_people_lookups_return_name_and_photo(pg_session_factory: Factory) -> None:
    org, (asha, ben), _ = await setup_org(pg_session_factory, "Asha", "Ben")
    await _set_photo(pg_session_factory, asha, slack_id="U_ASHA")
    async with pg_session_factory() as db:
        repo = UserRepository(db)
        by_id = await repo.get_people_by_ids({asha, ben})
        by_slack = await repo.get_people_by_slack_ids(org, {"U_ASHA", "U_NOBODY"})
    assert by_id == {asha: PersonCard("Asha", PHOTO), ben: PersonCard("Ben", None)}
    assert by_slack == {"U_ASHA": PersonCard("Asha", PHOTO)}


async def test_leave_views_carry_the_requester_photo(pg_session_factory: Factory) -> None:
    org, (emp, mgr), casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    await _set_photo(pg_session_factory, emp)
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=request.id, approve=True, note=None
        )
        await db.commit()
        calendar = await calendar_view(db, org, mgr, NOBODY, mon, mon)
        (read,) = await request_reads(
            db, org, [request], viewer=mgr, today=date.today(), private_ok=lambda _r: True
        )
    assert calendar.entries[0].user.avatar_url == PHOTO
    assert read.user.avatar_url == PHOTO
    assert read.decided_by is not None and read.decided_by.avatar_url is None


async def test_repo_contributors_carry_member_photos(pg_session_factory: Factory) -> None:
    org, (asha,), _ = await setup_org(pg_session_factory, "Asha")
    await _set_photo(pg_session_factory, asha)
    async with pg_session_factory() as db:
        repo = TrackedRepository(org_id=org, path="/tmp/app", name="app")
        db.add(repo)
        await db.flush()
        for n, (user_id, actor) in enumerate(((asha, "Asha"), (asha, "Asha"), (None, "Ghost"))):
            db.add(
                DevActivityLog(
                    org_id=org,
                    user_id=user_id,
                    repo_id=repo.id,
                    event_type="commit",
                    source="hook",
                    actor_name=actor,
                    commit_sha=f"{n:040x}",
                )
            )
        await db.commit()
        rows = await DevActivityLogRepository(db, org_id=org).top_contributors_for_repo(repo.id)
    assert [(r.actor_name, r.commit_count, r.avatar_url) for r in rows] == [
        ("Asha", 2, PHOTO),
        ("Ghost", 1, None),
    ]


async def test_bud_commit_contributors_carry_member_photos(pg_session_factory: Factory) -> None:
    org, (asha,), _ = await setup_org(pg_session_factory, "Asha")
    await _set_photo(pg_session_factory, asha)
    async with pg_session_factory() as db:
        bud = BUDDocument(org_id=org, bud_number=1, title="Checkout retries")
        db.add(bud)
        await db.flush()
        for n, (user_id, actor) in enumerate(((asha, "Asha"), (None, "Ghost"))):
            db.add(
                DevActivityLog(
                    org_id=org,
                    bud_id=bud.id,
                    user_id=user_id,
                    event_type="commit",
                    source="hook",
                    actor_name=actor,
                    commit_sha=f"{n:040x}",
                    metadata_={"author_email": f"{actor.lower()}@example.com"},
                )
            )
        await db.commit()
        me = SimpleNamespace(org_id=org)
        activity = await get_dev_activity(
            bud.id,
            role=None,
            exclude_role=None,
            current_user=me,
            db=db,  # type: ignore[arg-type]
        )
    photos = {c.author_name: c.avatar_url for c in activity.contributors}
    assert photos == {"Asha": PHOTO, "Ghost": None}
