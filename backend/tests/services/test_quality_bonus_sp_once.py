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

"""The BUD-completion quality bonus pays XP only; quality SP is paid once, at close.

``dev_quality_sp`` pays the quality skill points to every developer at
close. ``award_quality_bonus`` used to pay the same 0.5 SP again (under a
different source_ref, so the ledger's de-duplication never caught it), so
the assignee of a high-quality BUD got the bonus twice.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services import dev_stats, sp_service, xp_service


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self._rows


class _Db:
    """Answers the activity and task queries with one placeholder row each."""

    async def execute(self, _stmt: object) -> _Result:
        return _Result([object()])


@pytest.mark.parametrize("score", [95, 81])
async def test_high_quality_completion_pays_xp_but_no_sp(
    monkeypatch: pytest.MonkeyPatch, score: int
) -> None:
    xp_calls: list[dict[str, Any]] = []
    sp_spy = MagicMock()

    async def award_xp(_db: object, **kwargs: Any) -> None:
        xp_calls.append(kwargs)

    async def award_sp(*args: Any, **kwargs: Any) -> None:
        sp_spy(*args, **kwargs)

    monkeypatch.setattr(dev_stats, "calculate_effectiveness", lambda *_: {"score": score})
    monkeypatch.setattr(xp_service, "award_xp", award_xp)
    monkeypatch.setattr(sp_service, "award_sp", award_sp)

    bonus = await xp_service.award_quality_bonus(
        _Db(),  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        bud_id=uuid.uuid4(),
    )

    assert bonus == int(score * 0.3)
    assert [c["source"] for c in xp_calls] == ["quality_bonus"]
    sp_spy.assert_not_called()
