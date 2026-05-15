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

"""Shared mock helpers for the BUD chat endpoint test files.

Split out of the original ``test_bud_chat.py`` so the three behaviour-
specific test modules (basic / session / stage_gate) share the same
mock-construction surface without duplication.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.repositories.bud_section_session import ActiveJobPointer, ClaimResult


def make_bud(*, status: str = "design", bud_id: uuid.UUID | None = None) -> MagicMock:
    """Lightweight BUD stand-in — only the fields the handler reads."""
    bud = MagicMock()
    bud.id = bud_id or uuid.uuid4()
    bud.status = status
    bud.bud_number = 1
    bud.title = "Test BUD"
    bud.requirements_md = "spec"
    bud.tech_spec_md = ""
    bud.test_plan_md = ""
    return bud


def make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.org_id = uuid.uuid4()
    return user


def patch_repos(
    *,
    bud: MagicMock,
    active_session: Any = None,
    add_message: AsyncMock | None = None,
    claim_won: bool = True,
    claim_session_id: uuid.UUID | None = None,
    active_pointer: ActiveJobPointer | None = None,
) -> dict[str, MagicMock]:
    """Build the patch chain the endpoint imports during a request.

    ``claim_won`` defaults to True so the happy-path tests don't need to
    set up the claim explicitly. When ``False``, the handler raises 409
    ``chat_in_progress`` and ``active_pointer`` is what
    ``get_active_job_pointer`` returns for the response body.
    """
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=bud)
    bud_repo_cls = MagicMock(return_value=bud_repo)

    # When the claim wins, the repo returns the row's effective
    # session_id — either ``active_session.session_id`` (preserved on
    # update) or a freshly minted UUID (on insert).
    if claim_won:
        won_session_id = claim_session_id or (
            active_session.session_id if active_session is not None else uuid.uuid4()
        )
        claim_result = ClaimResult(won=True, session_id=won_session_id)
    else:
        claim_result = ClaimResult(won=False, session_id=None)

    session_repo = MagicMock()
    session_repo.get_active = AsyncMock(return_value=active_session)
    session_repo.try_claim_active_job = AsyncMock(return_value=claim_result)
    session_repo.get_active_job_pointer = AsyncMock(return_value=active_pointer)
    session_repo.clear_active_job = AsyncMock(return_value=None)
    session_repo.mark_active_job_running = AsyncMock(return_value=None)
    session_repo_cls = MagicMock(return_value=session_repo)

    chat_repo = MagicMock()
    chat_repo.add_message = add_message or AsyncMock(return_value=None)
    chat_repo_cls = MagicMock(return_value=chat_repo)

    design_repo = MagicMock()
    design_repo.get_by_id = AsyncMock(return_value=None)
    design_repo_cls = MagicMock(return_value=design_repo)

    return {
        "BUDRepository": bud_repo_cls,
        "BUDSectionSessionRepository": session_repo_cls,
        "BUDChatMessageRepository": chat_repo_cls,
        "BUDDesignRepository": design_repo_cls,
    }
