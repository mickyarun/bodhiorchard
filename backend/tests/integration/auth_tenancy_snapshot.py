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

"""Snapshot a tenant's seeded rows so a test can prove nothing changed.

Every column of every seeded row is read back, plus the child rows a
cross-org write could add (todos, comments, team members), so any write
that slips through scoping shows up as a difference.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, inspect, select

from app.models.base import BaseModel
from app.models.bud import BUDDocument
from app.models.bud_todo import BUDTodo
from app.models.bug import Bug
from app.models.bug_comment import BugComment
from app.models.design_system import DesignSystemRef
from app.models.feature import Feature
from app.models.leave_request import LeaveRequest
from app.models.notification import Notification
from app.models.office_location import OfficeLocation
from app.models.quiz_question import QuizQuestion
from app.models.role import Role, RolePermission
from app.models.team import Team, TeamMember
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser, User
from tests.integration.auth_tenancy_support import TenantRows
from tests.integration.leave_support import Factory


def _columns(row: BaseModel | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {c.key: getattr(row, c.key) for c in inspect(row).mapper.column_attrs}


async def snapshot(factory: Factory, rows: TenantRows) -> dict[str, Any]:
    """Every column of every seeded row, plus child-row counts."""
    targets: dict[str, tuple[type[BaseModel], uuid.UUID]] = {
        "bud": (BUDDocument, rows.bud),
        "bug": (Bug, rows.bug),
        "comment": (BugComment, rows.comment),
        "feature": (Feature, rows.feature),
        "repo": (TrackedRepository, rows.repo),
        "design_system": (DesignSystemRef, rows.design_system),
        "team": (Team, rows.team),
        "notification": (Notification, rows.notification),
        "office": (OfficeLocation, rows.office),
        "role": (Role, rows.role),
        "leave_request": (LeaveRequest, rows.leave_request),
        "question": (QuizQuestion, rows.question),
    }
    async with factory() as db:
        state: dict[str, Any] = {
            name: _columns(await db.get(model, row_id))
            for name, (model, row_id) in targets.items()
        }
        counts = {
            "todos": select(func.count()).where(BUDTodo.bud_id == rows.bud),
            "comments": select(func.count()).where(BugComment.bug_id == rows.bug),
            "team_members": select(func.count()).where(TeamMember.team_id == rows.team),
            "role_permissions": select(func.count()).where(RolePermission.role_id == rows.role),
        }
        for name, stmt in counts.items():
            state[name] = await db.scalar(stmt)
    return state


async def member_state(factory: Factory, user: uuid.UUID, org: uuid.UUID) -> dict[str, Any]:
    """A member's account row and their membership in ``org``."""
    async with factory() as db:
        membership = await db.scalar(
            select(OrgToUser).where(OrgToUser.user_id == user, OrgToUser.org_id == org)
        )
        return {"user": _columns(await db.get(User, user)), "membership": _columns(membership)}
