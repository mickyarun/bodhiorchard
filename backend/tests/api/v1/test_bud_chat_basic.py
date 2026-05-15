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

"""Baseline behaviour tests for the BUD chat endpoint.

Covers the not-found short-circuit. The full HTTP+DB harness isn't
wired here (see ``tests/conftest.py``), so the tests call the endpoint
handler directly with the repositories and ``create_job`` stubbed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.bud_chat import BUDChatRequest, chat_bud, get_active_chat_job
from app.schemas.jobs import JobState, JobStatusRead
from tests.api.v1._bud_chat_helpers import make_user


@pytest.mark.asyncio
async def test_chat_bud_404_when_bud_missing() -> None:
    """Missing BUD → ``HTTPException(404)`` before any further work."""
    user = make_user()
    db = MagicMock()
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=None)

    with (
        patch("app.api.v1.bud_chat.BUDRepository", return_value=bud_repo),
        pytest.raises(HTTPException) as ei,
    ):
        await chat_bud(
            bud_id=uuid.uuid4(),
            body=BUDChatRequest(message="hi", section="requirements_md"),
            current_user=user,
            db=db,
        )
    assert ei.value.status_code == 404


# ── GET /chat/active-job ────────────────────────────────────────────


def _make_running_status(job_id: str | None = None) -> JobStatusRead:
    return JobStatusRead(
        job_id=job_id or str(uuid.uuid4()),
        job_type="bud_chat",
        state=JobState.RUNNING,
        status_message="Reading file...",
    )


@pytest.mark.asyncio
async def test_active_chat_job_returns_none_when_idle() -> None:
    """No in-flight chat → endpoint returns None (renders as JSON ``null``)."""
    user = make_user()
    with patch("app.api.v1.bud_chat.find_active_job", return_value=None) as fn:
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
        )
    assert out is None
    fn.assert_called_once()


@pytest.mark.asyncio
async def test_active_chat_job_returns_status_when_running() -> None:
    """Live chat job → endpoint returns its :class:`JobStatusRead` verbatim."""
    user = make_user()
    expected = _make_running_status()
    with patch("app.api.v1.bud_chat.find_active_job", return_value=expected):
        out = await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
        )
    assert out is expected


@pytest.mark.asyncio
async def test_active_chat_job_scope_keys_no_design() -> None:
    """Match-payload for a non-design section carries ``design_id=None``."""
    user = make_user()
    bud_id = uuid.uuid4()
    with patch("app.api.v1.bud_chat.find_active_job", return_value=None) as fn:
        await get_active_chat_job(
            bud_id=bud_id,
            section="requirements_md",
            design_id=None,
            current_user=user,
        )
    job_type, match = fn.call_args.args
    assert job_type == "bud_chat"
    assert match == {
        "org_id": str(user.org_id),
        "bud_id": str(bud_id),
        "section": "requirements_md",
        "design_id": None,
    }


@pytest.mark.asyncio
async def test_active_chat_job_scope_keys_with_design() -> None:
    """Match-payload for the design section carries the stringified ``design_id``."""
    user = make_user()
    bud_id = uuid.uuid4()
    design_id = uuid.uuid4()
    with patch("app.api.v1.bud_chat.find_active_job", return_value=None) as fn:
        await get_active_chat_job(
            bud_id=bud_id,
            section="design",
            design_id=design_id,
            current_user=user,
        )
    _, match = fn.call_args.args
    assert match["design_id"] == str(design_id)
    assert match["section"] == "design"


@pytest.mark.asyncio
async def test_active_chat_job_cross_org_returns_none() -> None:
    """A different org's request matches no job (silent-empty, same as ``get_chat_history``).

    The underlying ``find_active_job`` filters by ``org_id`` in the
    match payload, so an org-B user querying an org-A BUD's chat finds
    nothing — exercised here by asserting the org_id key is the *caller*
    user's org_id, not the BUD's.
    """
    user = make_user()
    with patch("app.api.v1.bud_chat.find_active_job", return_value=None) as fn:
        await get_active_chat_job(
            bud_id=uuid.uuid4(),
            section="requirements_md",
            design_id=None,
            current_user=user,
        )
    _, match = fn.call_args.args
    assert match["org_id"] == str(user.org_id)
