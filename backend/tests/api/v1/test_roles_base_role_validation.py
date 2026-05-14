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

"""Handler-level tests for ``base_role_id`` validation on /v1/roles.

The phase auto-assigner joins through ``Role.base_role_id`` to resolve
CUSTOM roles to a UserRole. If a custom role's ``base_role_id`` points
at another CUSTOM row, or at an inactive row, members of that role
become invisible to auto-assignment forever — so the API rejects such
payloads up-front with 400 ``base_role_id must reference an active
system role.``.

Same handler-with-fakes pattern as ``test_bud_edit_gating.py``; no DB
scaffolding (see ``tests/conftest.py`` for the historical reason).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import roles as role_handlers
from app.models.role import RoleScopeType
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate

# ``fake_user`` and ``fake_db`` come from tests/api/v1/conftest.py.


def _patch_role_repo(
    monkeypatch: pytest.MonkeyPatch,
    *,
    base_role: SimpleNamespace | None,
    role_to_update: SimpleNamespace | None = None,
    read_dto: RoleRead | None = None,
) -> MagicMock:
    """Stub RoleRepository with the methods the role handlers actually call."""

    async def _get_by_id(role_id: uuid.UUID) -> SimpleNamespace | None:
        if role_to_update is not None and role_id == role_to_update.id:
            return role_to_update
        return base_role

    repo = MagicMock(
        get_by_id=AsyncMock(side_effect=_get_by_id),
        create=AsyncMock(),
        replace_permissions=AsyncMock(),
        read=AsyncMock(return_value=read_dto),
    )
    monkeypatch.setattr(role_handlers, "RoleRepository", MagicMock(return_value=repo))
    return repo


def _system_role(name: str = "tech_lead", *, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        description=None,
        scope_type=RoleScopeType.SYSTEM,
        is_active=is_active,
        base_role_id=None,
        base_role=None,
        role_permissions=[],
    )


def _custom_role(name: str = "Senior Architect") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        description=None,
        scope_type=RoleScopeType.CUSTOM,
        is_active=True,
        base_role_id=None,
        base_role=None,
        role_permissions=[],
    )


# ── POST /v1/roles ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_role_rejects_custom_base_role(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """``base_role_id`` pointing at a CUSTOM role → 400."""
    bad_base = _custom_role(name="Existing Custom Role")
    _patch_role_repo(monkeypatch, base_role=bad_base)

    body = RoleCreate(
        name="Senior Architect",
        base_role_id=bad_base.id,
        permission_ids=[uuid.uuid4()],
    )
    with pytest.raises(HTTPException) as excinfo:
        await role_handlers.create_role(body=body, current_user=fake_user, db=fake_db)
    assert excinfo.value.status_code == 400
    assert "system role" in excinfo.value.detail


@pytest.mark.asyncio
async def test_create_role_rejects_inactive_system_base(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """``base_role_id`` pointing at a deactivated system role → 400.

    An inactive base would leave the new custom role permanently
    invisible to auto-assignment because the repository SQL filters
    by ``is_active=True`` on the joined system row.
    """
    inactive_base = _system_role(is_active=False)
    _patch_role_repo(monkeypatch, base_role=inactive_base)

    body = RoleCreate(
        name="Senior Architect",
        base_role_id=inactive_base.id,
        permission_ids=[uuid.uuid4()],
    )
    with pytest.raises(HTTPException) as excinfo:
        await role_handlers.create_role(body=body, current_user=fake_user, db=fake_db)
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_create_role_success_returns_read_dto(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Happy path returns the DTO produced by ``RoleRepository.read``.

    Behaviour check (not implementation): given a valid system base role
    and a returning ``read`` stub, the handler hands back exactly that
    DTO. Catches the production bug — the handler must build the
    response through the repo's read function, not by touching ORM
    relationships on the freshly-inserted row.
    """
    good_base = _system_role(name="tech_lead", is_active=True)
    expected = RoleRead(
        id=uuid.uuid4(),
        name="Senior Architect",
        description=None,
        scope_type="custom",
        is_active=True,
        base_role_id=good_base.id,
        base_role_name=good_base.name,
        permissions=[],
    )
    _patch_role_repo(monkeypatch, base_role=good_base, read_dto=expected)

    body = RoleCreate(
        name="Senior Architect",
        base_role_id=good_base.id,
        permission_ids=[uuid.uuid4()],
    )
    result = await role_handlers.create_role(body=body, current_user=fake_user, db=fake_db)
    assert result == expected


def test_create_role_rejects_empty_permission_ids() -> None:
    """``RoleCreate`` must refuse a role with zero permissions at validation time.

    A role with no permissions can't grant any access, so admins who
    saved with an empty form would create a useless row. The frontend
    disables Save in this state too — this guard ensures the backend
    rejects any client that bypasses the UI.
    """
    with pytest.raises(ValidationError):
        RoleCreate(
            name="Senior Architect",
            base_role_id=uuid.uuid4(),
            permission_ids=[],
        )


def test_update_role_rejects_empty_permission_ids_when_present() -> None:
    """``RoleUpdate.permission_ids`` is optional but never an empty list.

    ``None`` means "don't touch permissions"; ``[]`` would clear them
    all, which orphans every member of the role. Use DELETE instead.
    """
    with pytest.raises(ValidationError):
        RoleUpdate(permission_ids=[])
    # ``None`` (omitted from payload) stays valid.
    RoleUpdate(name="Renamed").model_dump(exclude_unset=True)


@pytest.mark.asyncio
async def test_create_role_rejects_unknown_base_role(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """``base_role_id`` referencing a deleted/missing row → 400."""
    _patch_role_repo(monkeypatch, base_role=None)

    body = RoleCreate(
        name="Senior Architect",
        base_role_id=uuid.uuid4(),
        permission_ids=[uuid.uuid4()],
    )
    with pytest.raises(HTTPException) as excinfo:
        await role_handlers.create_role(body=body, current_user=fake_user, db=fake_db)
    assert excinfo.value.status_code == 400


# ── PUT /v1/roles/{role_id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_role_rejects_invalid_base(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """Re-pointing a custom role at a CUSTOM/inactive/missing base → 400."""
    target = _custom_role()
    bad_base = _custom_role(name="Another Custom")
    repo = _patch_role_repo(monkeypatch, base_role=bad_base, role_to_update=target)

    body = RoleUpdate(base_role_id=bad_base.id)
    with pytest.raises(HTTPException) as excinfo:
        await role_handlers.update_role(role_id=target.id, body=body, _user=fake_user, db=fake_db)
    assert excinfo.value.status_code == 400
    # The repository's update path must not have replaced permissions
    # when validation failed.
    repo.replace_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_update_role_rejects_system_role_modification(
    monkeypatch: pytest.MonkeyPatch,
    fake_user: SimpleNamespace,
    fake_db: MagicMock,
) -> None:
    """System roles cannot be modified — 403 takes precedence over any base check."""
    target = _system_role(name="tech_lead")
    _patch_role_repo(monkeypatch, base_role=None, role_to_update=target)

    body = RoleUpdate(name="Renamed System Role")
    with pytest.raises(HTTPException) as excinfo:
        await role_handlers.update_role(role_id=target.id, body=body, _user=fake_user, db=fake_db)
    assert excinfo.value.status_code == 403
