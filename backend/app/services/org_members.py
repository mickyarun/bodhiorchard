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

"""Checks that a user named in a request body belongs to the caller's org.

A handler scopes the row it writes by ``org_id``, but ids inside the body
(an assignee) point at other rows. Users are global, so an assignee must
be checked against the org's memberships explicitly, or a row in one org
can name, and show the name of, a member of another.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository


async def assert_new_assignee_in_org(
    db: AsyncSession,
    org_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
    current_id: uuid.UUID | None,
) -> None:
    """Raise 404 unless a newly chosen assignee is a member of ``org_id``.

    Clearing the assignee, or resending the one already stored, passes
    unchecked: an edit to something else shouldn't fail because the current
    assignee has since left. 404 rather than 403, so the answer is the same
    whether the user exists in another org or not at all.
    """
    if assignee_id is None or assignee_id == current_id:
        return
    if not await UserRepository(db).is_member_of_org(assignee_id, org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")
