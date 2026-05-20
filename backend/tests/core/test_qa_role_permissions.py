# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Pin the QA role's default permission set.

Regression guard for the bug where QA users got HTTP 403 on
``POST /buds/{id}/qa/evidence/{tc}`` because the endpoint required
``buds:edit`` and the QA role only carried ``buds:view``. The fix
introduced ``buds:test`` (record test results / upload evidence) as a
separate permission and added it to the QA role.

These tests pin the catalog + role contract so a future edit to
``DEFAULT_SYSTEM_ROLES`` can't silently take the perm away again, and
also confirm the separation of concerns: ``buds:edit`` (spec edit) is
NOT granted to QA — only the narrower test/evidence permission is.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core import deps
from app.core.deps import require_permissions
from app.core.permissions import (
    ALL_PERMISSION_IDS,
    DEFAULT_SYSTEM_ROLES,
    PERMISSION_CATEGORIES,
    RoleDef,
)


def _role(name: str) -> RoleDef:
    for role in DEFAULT_SYSTEM_ROLES:
        if role.name == name:
            return role
    raise AssertionError(f"system role {name!r} missing from DEFAULT_SYSTEM_ROLES")


def test_buds_test_permission_is_registered() -> None:
    # The seeder copies PERMISSION_CATEGORIES into the ``permissions``
    # table on startup. Drop this assertion if the perm ever moves
    # categories — silently dropping it breaks every QA org on next deploy.
    assert "buds:test" in ALL_PERMISSION_IDS
    buds_category = next(c for c in PERMISSION_CATEGORIES if c.key == "BUDS")
    assert any(p.resource_id == "buds:test" for p in buds_category.permissions)


def test_qa_role_can_view_and_test_buds() -> None:
    qa = _role("qa")
    assert "buds:view" in qa.permission_ids
    assert "buds:test" in qa.permission_ids


def test_qa_role_cannot_edit_or_approve_buds() -> None:
    # Separation of concerns: QA executes tests but does not edit
    # specs/plans (``buds:edit``) or approve phase gates (``buds:approve``).
    qa = _role("qa")
    assert "buds:edit" not in qa.permission_ids
    assert "buds:approve" not in qa.permission_ids
    assert "buds:create" not in qa.permission_ids


def test_editor_roles_still_pass_via_buds_edit() -> None:
    # The QA endpoints use ``require_permissions("buds:edit", "buds:test",
    # mode="any")``, so editor roles must keep ``buds:edit`` to retain
    # upload-evidence access without needing the new perm too.
    for role_name in ("manager", "developer"):
        role = _role(role_name)
        assert "buds:edit" in role.permission_ids, f"{role_name} lost buds:edit"


# ── Dependency-layer integration ───────────────────────────────────────
#
# The catalog tests above pin role configuration. These tests pin the
# *resolver* — i.e. that ``require_permissions("buds:edit", "buds:test",
# mode="any")`` actually lets a QA-perm user through. If ``mode="any"``
# semantics ever regress, the catalog tests would still pass while QA
# returns to HTTP 403 in production. This guard catches that.


def _fake_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4(), role=None, role_id=uuid.uuid4())


async def _run_dep(user_perms: set[str], *required: str, mode: str = "any") -> None:
    """Invoke the inner ``_check`` of ``require_permissions`` with a fake user."""
    dep = require_permissions(*required, mode=mode)  # type: ignore[arg-type]
    # ``RoleRepository.get_role_name`` is consulted only for the
    # org_owner short-circuit — return ``"qa"`` so we exercise the
    # perm-check branch instead.
    with (
        patch.object(deps, "get_user_permissions", new=AsyncMock(return_value=user_perms)),
        patch.object(deps, "RoleRepository") as role_repo_cls,
    ):
        role_repo_cls.return_value = SimpleNamespace(get_role_name=AsyncMock(return_value="qa"))
        await dep(current_user=_fake_user(), db=AsyncMock())


async def test_qa_perms_pass_upload_evidence_gate() -> None:
    # QA holds {buds:view, buds:test}. The endpoint gate is
    # ("buds:edit", "buds:test", mode="any"). Must NOT raise.
    await _run_dep({"buds:view", "buds:test"}, "buds:edit", "buds:test", mode="any")


async def test_editor_perms_pass_same_gate() -> None:
    # Manager/Developer hold buds:edit but NOT buds:test. Must NOT raise.
    await _run_dep({"buds:view", "buds:edit"}, "buds:edit", "buds:test", mode="any")


async def test_viewer_only_perms_rejected() -> None:
    # Viewer holds buds:view only. Must raise 403 — the regression we are
    # actually guarding against.
    with pytest.raises(HTTPException) as excinfo:
        await _run_dep({"buds:view"}, "buds:edit", "buds:test", mode="any")
    assert excinfo.value.status_code == 403
