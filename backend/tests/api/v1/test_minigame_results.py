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

"""Handler tests for the bridge-only mini-game score endpoint.

The endpoint is the ONLY path that records a mini-game score now — the client
can no longer self-report. These pin the security-relevant behaviour: org
membership is enforced, the write is idempotent on session_id, and a genuine
new org record schedules the Slack broadcast. Handler-with-fakes pattern (same
as ``test_roles_base_role_validation.py``) — no DB scaffolding.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException, status

from app.api.v1 import internal_colyseus as mod
from app.repositories.minigame import LeaderboardRow
from app.schemas.minigame import MinigameResultsBody

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RIVAL_ID = uuid.uuid4()


def _body(score: int = 12, session_id: str = "minigame-abc") -> MinigameResultsBody:
    return MinigameResultsBody(
        sessionId=session_id,
        orgId=ORG_ID,
        userId=USER_ID,
        userName="Me",
        game="firefly",
        score=score,
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_member: bool = True,
    claimed: bool = True,
    top_before: list[LeaderboardRow] | None = None,
    submit_result: dict[str, object] | None = None,
) -> dict[str, MagicMock]:
    """Stub the module-level collaborators the handler calls."""
    user_repo = MagicMock(is_member_of_org=AsyncMock(return_value=is_member))
    monkeypatch.setattr(mod, "UserRepository", MagicMock(return_value=user_repo))

    mg_repo = MagicMock(
        try_claim_session=AsyncMock(return_value=claimed),
        get_user_game=AsyncMock(
            return_value=SimpleNamespace(best_score=20, current_streak=3, best_streak=4)
        ),
    )
    monkeypatch.setattr(mod, "MinigameRepository", MagicMock(return_value=mg_repo))

    monkeypatch.setattr(mod, "get_leaderboard", AsyncMock(return_value=top_before or []))
    monkeypatch.setattr(
        mod,
        "submit_score",
        AsyncMock(
            return_value=submit_result
            or {
                "game": "firefly",
                "score": 12,
                "best_score": 12,
                "is_new_best": True,
                "current_streak": 1,
                "best_streak": 1,
                "first_play_today": True,
            }
        ),
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(mod, "broadcast_high_score", broadcast)
    return {"user_repo": user_repo, "mg_repo": mg_repo, "broadcast": broadcast}


async def test_rejects_non_member(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, is_member=False)
    with pytest.raises(HTTPException) as exc:
        await mod.post_minigame_results(
            body=_body(), background_tasks=BackgroundTasks(), _=None, db=AsyncMock()
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


async def test_records_a_first_time_session(monkeypatch: pytest.MonkeyPatch) -> None:
    fakes = _patch(monkeypatch, claimed=True)
    db = AsyncMock()
    result = await mod.post_minigame_results(
        body=_body(), background_tasks=BackgroundTasks(), _=None, db=db
    )
    assert result.recorded is True
    assert result.best_score == 12
    fakes["mg_repo"].try_claim_session.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_idempotent_retry_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, claimed=False)
    db = AsyncMock()
    result = await mod.post_minigame_results(
        body=_body(), background_tasks=BackgroundTasks(), _=None, db=db
    )
    assert result.recorded is False
    assert result.best_score == 20  # from the existing aggregate
    mod.submit_score.assert_not_awaited()  # type: ignore[attr-defined]
    db.commit.assert_not_awaited()


async def test_new_org_record_schedules_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    prev = LeaderboardRow(user_id=RIVAL_ID, user_name="Ada", best_score=8, plays=2)
    _patch(monkeypatch, claimed=True, top_before=[prev])
    tasks = BackgroundTasks()
    await mod.post_minigame_results(
        body=_body(score=12), background_tasks=tasks, _=None, db=AsyncMock()
    )
    assert len(tasks.tasks) == 1  # broadcast scheduled (dethroned Ada)


async def test_self_pad_does_not_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    # The standing record is already this player's — beating yourself is no DM.
    prev = LeaderboardRow(user_id=USER_ID, user_name="Me", best_score=8, plays=1)
    _patch(monkeypatch, claimed=True, top_before=[prev])
    tasks = BackgroundTasks()
    await mod.post_minigame_results(
        body=_body(score=12), background_tasks=tasks, _=None, db=AsyncMock()
    )
    assert len(tasks.tasks) == 0
