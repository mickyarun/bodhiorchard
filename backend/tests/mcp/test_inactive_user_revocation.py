# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Tests for member-offboarding token revocation.

Two paths must both be in place — testing them together because either
alone leaves a security gap:

1. ``UserMCPTokenRepository.delete_all_for_user`` drops every token row
   for a user on deactivation / merge. Without it, ``is_active=False``
   leaves tokens live (the FK CASCADE only fires on hard DELETE).
2. ``verify_mcp_token`` rejects with 401 when the resolved user has
   ``is_active=False``. Belt-and-braces: a missed revoke call site
   still can't authenticate to /mcp/*.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.mcp.auth import verify_mcp_token
from app.repositories.user_mcp_token import UserMCPTokenRepository

# ── 1. Repo: delete_all_for_user issues a single-WHERE DELETE on user_id ──


async def _capture_delete_sql(user_id: uuid.UUID) -> str:
    """Run delete_all_for_user against a mock DB and return compiled SQL."""
    captured: dict[str, Any] = {}

    async def _execute(stmt: Any) -> MagicMock:
        captured["stmt"] = stmt
        result = MagicMock()
        result.rowcount = 0
        return result

    db = MagicMock(execute=AsyncMock(side_effect=_execute))
    repo = UserMCPTokenRepository(db)
    await repo.delete_all_for_user(user_id)
    return str(
        captured["stmt"].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
async def test_delete_all_for_user_filters_by_user_id_only() -> None:
    """SQL must DELETE only on user_id — not on org_id, not on name.

    Cross-org revocation is the intended semantic: a deactivated user
    must lose every token they own, regardless of which org issued it.
    """
    uid = uuid.uuid4()
    sql = await _capture_delete_sql(uid)
    sql_lower = sql.lower()
    assert sql_lower.startswith("delete from user_mcp_tokens")
    assert f"user_id = '{uid}'" in sql_lower
    # Guard against an accidental scope narrowing in a future refactor.
    assert "org_id" not in sql_lower
    assert "name" not in sql_lower


# ── 2. Auth: verify_mcp_token rejects when ut.user.is_active is False ──


def _fake_token_row(*, is_active: bool) -> MagicMock:
    """Build a UserMCPToken mock that bcrypt-verifies and links to a user."""
    org = MagicMock(id=uuid.uuid4(), slug="acme")
    user = MagicMock(id=uuid.uuid4(), is_active=is_active)
    return MagicMock(
        id=uuid.uuid4(),
        org_id=org.id,
        user_id=user.id,
        token_hash="$2b$12$fake",  # value doesn't matter — verify_password is patched
        expires_at=None,
        organization=org,
        user=user,
    )


@pytest.mark.asyncio
async def test_verify_mcp_token_rejects_inactive_user(monkeypatch: Any) -> None:
    """Even a valid, unexpired token must 401 if its owner is deactivated."""
    inactive_token = _fake_token_row(is_active=False)

    async def _list_by_prefix(self: Any, prefix: str) -> list[Any]:
        return [inactive_token]

    monkeypatch.setattr(
        UserMCPTokenRepository, "list_by_prefix_with_relations", _list_by_prefix
    )
    monkeypatch.setattr("app.mcp.auth.verify_password", lambda token, hash_: True)

    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await verify_mcp_token(db=db, authorization="Bearer fake-token-string")
    assert exc.value.status_code == 401
    assert "deactivated" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_mcp_token_accepts_active_user(monkeypatch: Any) -> None:
    """Sanity check the test doesn't accidentally reject every token."""
    active_token = _fake_token_row(is_active=True)

    async def _list_by_prefix(self: Any, prefix: str) -> list[Any]:
        return [active_token]

    monkeypatch.setattr(
        UserMCPTokenRepository, "list_by_prefix_with_relations", _list_by_prefix
    )
    monkeypatch.setattr("app.mcp.auth.verify_password", lambda token, hash_: True)
    # The is_active=True path schedules a background task; stub it so the
    # test doesn't actually create an asyncio task against a mock session.
    monkeypatch.setattr("app.mcp.auth._schedule_last_used", lambda *a, **kw: None)

    db = MagicMock()
    result = await verify_mcp_token(db=db, authorization="Bearer fake-token-string")
    assert result.org is active_token.organization
    assert result.user is active_token.user
    assert result.token_id == active_token.id
