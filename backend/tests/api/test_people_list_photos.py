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

"""People lists put the stored ``avatar_url`` on the wire beside the name.

These responses read the photo off a ``User`` row their query already
loads, so plain objects stand in for the ORM rows here; the queries that
had to change are covered in ``tests/integration``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1 import bug_comments, learnings, members, skills, triage_sessions
from app.repositories.user import PersonCard
from app.schemas.bud import BUDListItem, BUDRead
from app.schemas.bug import BugCommentRead

PHOTO = "/api/v1/employees/avatars/0123456789abcdef0123456789abcdef"
NOW = datetime.now(UTC)


def _user(avatar_url: str | None = PHOTO, **over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "name": "Asha Rao",
        "email": "asha@example.com",
        "is_active": True,
        "avatar_url": avatar_url,
    }
    return SimpleNamespace(**(base | over))


class _Org:
    def __init__(self, db: Any) -> None:
        pass

    async def get_for_user(self, user: Any) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4())


@pytest.mark.parametrize("schema", [BUDListItem, BUDRead])
def test_bud_responses_carry_the_assignee_photo(schema: type[BUDListItem | BUDRead]) -> None:
    # The board writes the single-BUD response back into its list, so both carry it.
    bud = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        metadata_=None,
        bud_number=7,
        title="Checkout",
        status="development",
        priority="P2",
        assignee_id=uuid.uuid4(),
        assignee=_user(),
        created_at=NOW,
        updated_at=NOW,
    )
    item = schema.model_validate(bud)
    assert (item.assignee_name, item.assignee_avatar_url) == ("Asha Rao", PHOTO)


async def test_member_directory_carries_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Users:
        def __init__(self, db: Any, org_id: Any = None) -> None:
            pass

        async def list_with_membership(self, org_id: Any) -> list[SimpleNamespace]:
            return [_user(), _user(None, name="Ben", email="ben@example.com")]

    monkeypatch.setattr(members, "OrganizationRepository", _Org)
    monkeypatch.setattr(members, "UserRepository", _Users)
    rows = await members.list_member_directory(current_user=_user(), db=None)  # type: ignore[arg-type]
    assert [r.avatar_url for r in rows] == [PHOTO, None]


async def test_skill_profiles_carry_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _user()
    profile = SimpleNamespace(
        user_id=user.id,
        module="billing",
        skill_score=0.8,
        languages=["python"],
        touch_count=3,
        lines_added=10,
        lines_removed=2,
    )

    class _Skills:
        def __init__(self, db: Any, org_id: Any = None) -> None:
            pass

        async def list_with_users(self) -> list[tuple[Any, Any]]:
            return [(profile, user)]

    monkeypatch.setattr(skills, "OrganizationRepository", _Org)
    monkeypatch.setattr(skills, "SkillProfileRepository", _Skills)
    (read,) = await skills.list_profiles(current_user=user, db=None)  # type: ignore[arg-type]
    assert read.model_dump(by_alias=True)["avatarUrl"] == PHOTO


def test_learnings_top_contributors_carry_photos() -> None:
    rows = learnings._build_top_contributors([(_user(), 2, 9, 3)])  # type: ignore[list-item]
    assert rows[0].avatar_url == PHOTO


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        pytest.param(PersonCard("Asha Rao", PHOTO), ("Asha Rao", PHOTO), id="member"),
        pytest.param(None, (None, None), id="author-gone"),
    ],
)
def test_bug_comments_carry_the_author_photo(
    author: PersonCard | None, expected: tuple[str | None, str | None]
) -> None:
    comment = SimpleNamespace(
        id=uuid.uuid4(),
        bug_id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        body="Repro attached",
        edited_at=None,
        deleted_at=None,
        created_at=NOW,
    )
    read: BugCommentRead = bug_comments._comment_read(comment, author)  # type: ignore[arg-type]
    body = read.model_dump(by_alias=True)
    assert (body["authorName"], body["authorAvatarUrl"]) == expected


@pytest.mark.parametrize(
    ("slack_id", "expected"),
    [
        pytest.param("U_ASHA", ("Asha Rao", PHOTO), id="linked-member"),
        pytest.param("U_SLACK_ONLY", (None, None), id="slack-only"),
    ],
)
def test_triage_requester_carries_the_member_photo(
    slack_id: str, expected: tuple[str | None, str | None]
) -> None:
    session = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        slack_channel="C1",
        thread_ts="1.0",
        requester_slack_id=slack_id,
        requester_name="asha",
        original_text="Export is broken",
        status="pending",
        priority=None,
        feature_name=None,
        triage_context=None,
        bud_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    people = {"U_ASHA": PersonCard("Asha Rao", PHOTO)}
    read = triage_sessions._with_requester(session, people)  # type: ignore[arg-type]
    assert (read.requester_display_name, read.requester_avatar_url) == expected
