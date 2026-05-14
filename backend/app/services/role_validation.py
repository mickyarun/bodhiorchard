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

"""Role validation + read helpers.

Layering follows the same pattern as ``services/bud_edit_policy.py``:
:func:`is_valid_base_role` is a pure domain predicate (no HTTP, no I/O),
and :func:`assert_valid_base_role` / :func:`read_or_404` are thin
HTTP wrappers that fetch via the repository and raise ``HTTPException``.
Domain callers (background jobs, non-HTTP code) use the predicate;
FastAPI handlers use the assert/read forms.
"""

import uuid

from fastapi import HTTPException, status

from app.models.role import Role, RoleScopeType
from app.repositories.role import RoleRepository
from app.schemas.role import RoleRead


def is_valid_base_role(role: Role | None) -> bool:
    """Return ``True`` iff ``role`` is an acceptable inheritance target.

    The phase auto-assigner resolves CUSTOM roles to a ``UserRole`` by
    joining through ``Role.base_role_id`` to a SYSTEM row and matching
    the parent's ``name``. The parent must therefore be:

    - Present (not ``None``) — ``base_role_id`` may dangle if the
      target row was deleted.
    - SYSTEM-scoped — pointing at another CUSTOM role would chain
      the lookup indefinitely and never resolve to a UserRole.
    - Active — an inactive system role is excluded by the repository
      SQL (``... AND base.is_active = TRUE``), so members of a custom
      role inheriting from it would be invisible to auto-assignment.
    """
    return role is not None and role.scope_type == RoleScopeType.SYSTEM and role.is_active


async def assert_valid_base_role(role_repo: RoleRepository, base_role_id: uuid.UUID) -> None:
    """HTTP wrapper: fetch the candidate base role, raise 400 if not eligible.

    Pure check lives in :func:`is_valid_base_role`; this form is the one
    FastAPI handlers should call.
    """
    base = await role_repo.get_by_id(base_role_id)
    if not is_valid_base_role(base):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_role_id must reference an active system role.",
        )


async def read_or_404(role_repo: RoleRepository, role_id: uuid.UUID) -> RoleRead:
    """Return ``role_repo.read(role_id)`` or raise 404 — handler shortcut."""
    dto = await role_repo.read(role_id)
    if dto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return dto
