# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Defensive 409 when an IntegrityError slips past the duplicate-name check.

The documented duplicate-name case is handled by the pre-check in
``create_my_mcp_token``. The IntegrityError fallback exists for the
case the pre-check can't see — typically a leftover legacy unique
index (see migration ``555236b875ed``). Without the fallback, a
drifted DB returns a 500 stack trace; with it, the user gets an
actionable 409.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.v1 import me as me_handlers


@pytest.mark.asyncio
async def test_create_mcp_token_converts_integrity_error_to_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="ada@example.com",
    )

    # Pre-check passes — the duplicate-name path isn't what we're
    # testing here.
    monkeypatch.setattr(
        me_handlers.UserMCPTokenRepository,
        "get_by_user_org_name",
        AsyncMock(return_value=None),
    )

    db = MagicMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock(
        side_effect=IntegrityError(
            statement="INSERT INTO user_mcp_tokens ...",
            params=None,
            orig=Exception("duplicate key value violates unique constraint"),
        )
    )

    body = me_handlers.MCPTokenCreate(name="test", expires_in_days=90)

    with pytest.raises(HTTPException) as exc:
        await me_handlers.create_my_mcp_token(body=body, current_user=user, db=db)

    assert exc.value.status_code == 409
    assert "uniqueness constraint" in str(exc.value.detail)
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_mcp_token_duplicate_name_409_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the pre-check already knows about the duplicate, the
    integrity-error fallback should never run."""
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="ada@example.com",
    )

    monkeypatch.setattr(
        me_handlers.UserMCPTokenRepository,
        "get_by_user_org_name",
        AsyncMock(return_value=MagicMock()),  # row exists
    )

    db = MagicMock(flush=AsyncMock(), rollback=AsyncMock())

    body = me_handlers.MCPTokenCreate(name="duplicate", expires_in_days=90)

    with pytest.raises(HTTPException) as exc:
        await me_handlers.create_my_mcp_token(body=body, current_user=user, db=db)

    assert exc.value.status_code == 409
    assert "Revoke it first" in str(exc.value.detail)
    # No flush happened — pre-check raised before the INSERT.
    db.flush.assert_not_awaited()


# Silence unused-import warnings for params we reference in type hints.
_ = Any
