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

"""Who may see whose leave in reports and on a member's history."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.permission_deps import PermissionSet
from app.services.leave import report_scope as module
from app.services.leave.errors import LeaveForbiddenError
from app.services.leave.report_scope import ReportScope, may_view_member_leave, report_scope

ORG = uuid.uuid4()
VIEWER = SimpleNamespace(id=uuid.uuid4(), org_id=ORG)
REPORT, OTHER = uuid.uuid4(), uuid.uuid4()


def perms(*ids: str, owner: bool = False) -> PermissionSet:
    return PermissionSet(ids=frozenset(ids), is_owner=owner)


@pytest.fixture
def direct_reports(monkeypatch: pytest.MonkeyPatch) -> set[uuid.UUID]:
    reports: set[uuid.UUID] = set()

    async def fake(_db: Any, org_id: uuid.UUID, manager: uuid.UUID) -> set[uuid.UUID]:
        assert (org_id, manager) == (ORG, VIEWER.id)
        return reports

    monkeypatch.setattr(module, "reports_of", fake)
    return reports


async def test_reports_holders_and_the_owner_see_everyone(direct_reports: set[uuid.UUID]) -> None:
    for p in (perms("leave:reports"), perms(owner=True)):
        assert (await report_scope(None, VIEWER, p)).is_all  # type: ignore[arg-type]


async def test_a_manager_sees_direct_reports_only(direct_reports: set[uuid.UUID]) -> None:
    direct_reports.add(REPORT)
    scope = await report_scope(None, VIEWER, perms())  # type: ignore[arg-type]
    assert scope.user_ids == {REPORT}
    # leave:approve alone doesn't open reports: it is about deciding, not exporting.
    assert (await report_scope(None, VIEWER, perms("leave:approve"))).user_ids == {REPORT}  # type: ignore[arg-type]


async def test_someone_with_no_reports_is_refused(direct_reports: set[uuid.UUID]) -> None:
    with pytest.raises(LeaveForbiddenError):
        await report_scope(None, VIEWER, perms("leave:configure"))  # type: ignore[arg-type]


def test_narrowing_to_one_person_never_widens() -> None:
    mine = ReportScope(frozenset({REPORT}))
    assert mine.narrow(REPORT).user_ids == {REPORT}
    assert mine.narrow(OTHER).user_ids == frozenset()
    assert mine.narrow(None) is mine
    assert ReportScope(None).narrow(OTHER).user_ids == {OTHER}
    assert not mine.allows(OTHER) and ReportScope(None).allows(OTHER)


async def test_member_leave_visibility(direct_reports: set[uuid.UUID]) -> None:
    direct_reports.add(REPORT)
    view = may_view_member_leave
    assert await view(None, VIEWER, perms(), VIEWER.id)  # type: ignore[arg-type]
    assert await view(None, VIEWER, perms(), REPORT)  # type: ignore[arg-type]
    assert not await view(None, VIEWER, perms("leave:configure"), OTHER)  # type: ignore[arg-type]
    for p in (perms("leave:approve"), perms("leave:reports"), perms(owner=True)):
        assert await view(None, VIEWER, p, OTHER)  # type: ignore[arg-type]
