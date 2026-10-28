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

    This is the one assignee check for every org-scoped row that names an
    assignee (BUDs, todos and bugs), so the rule below is the same for all:

    - Clearing the assignee (``None``) always passes.
    - Resending the assignee already stored on the row (``assignee_id ==
      current_id``) is a no-op and passes, even if that person has since
      left the org. Forms send the whole row back, so an edit to something
      else must not fail because of who it was assigned to before; and the
      write stores the same value, so nothing new crosses an org boundary.
    - Any other id must be a current member of ``org_id``. Once the stored
      assignee is changed or cleared, someone who has left can't be set
      again.

    404 rather than 403, so the answer is the same whether the user exists
    in another org or not at all.
    """
    if assignee_id is None or assignee_id == current_id:
        return
    if not await UserRepository(db).is_member_of_org(assignee_id, org_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")
