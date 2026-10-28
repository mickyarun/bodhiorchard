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

"""How a Jira candidate is classified by its distance to the nearest BUD.

The nearest-neighbour query is replaced so each case pins one distance;
the query itself is exercised on Postgres in
``tests/integration/test_jira_dedup_scope.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services import jira_dedup

BUD_ID = uuid.uuid4()


def _nearest(monkeypatch: pytest.MonkeyPatch, found: tuple[uuid.UUID, int, float] | None) -> None:
    async def _find(_self: Any, _vector: list[float], **_: Any) -> Any:
        return found

    monkeypatch.setattr(jira_dedup.BUDRepository, "find_nearest_neighbor", _find)


async def _check(**kwargs: Any) -> jira_dedup.DedupResult:
    return await jira_dedup.check_semantic_duplicate(
        None,  # type: ignore[arg-type]
        uuid.uuid4(),
        [0.0] * 384,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("distance", "duplicate", "review", "matched"),
    [
        (0.0, True, False, True),
        (0.2499, True, False, True),
        (0.25, False, True, True),
        (0.3999, False, True, True),
        (0.40, False, False, False),
        (1.5, False, False, False),
    ],
)
async def test_thresholds_are_half_open(
    monkeypatch: pytest.MonkeyPatch,
    distance: float,
    duplicate: bool,
    review: bool,
    matched: bool,
) -> None:
    """Below 0.25 skips, [0.25, 0.40) asks a human, 0.40 and up is new."""
    _nearest(monkeypatch, (BUD_ID, 7, distance))
    result = await _check()
    assert (result.is_duplicate, result.needs_review) == (duplicate, review)
    assert result.matched_bud_id == (BUD_ID if matched else None)
    assert result.matched_bud_number == (7 if matched else None)
    assert result.distance == round(distance, 4)


async def test_no_embedded_buds_means_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    _nearest(monkeypatch, None)
    result = await _check()
    assert (result.is_duplicate, result.needs_review, result.distance) == (False, False, None)
    assert result.note == "No existing BUDs with embeddings"


async def test_the_note_names_the_matched_bud(monkeypatch: pytest.MonkeyPatch) -> None:
    _nearest(monkeypatch, (BUD_ID, 42, 0.31234))
    result = await _check()
    assert result.note == "May overlap with BUD-42 (distance=0.312)"
    assert result.distance == 0.3123


async def test_excluded_ids_reach_the_query(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def _find(_self: Any, _vector: list[float], **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(jira_dedup.BUDRepository, "find_nearest_neighbor", _find)
    await _check(exclude_bud_ids={BUD_ID})
    assert seen == {"exclude_bud_ids": [BUD_ID]}
    await _check(exclude_bud_ids=set())
    assert seen == {"exclude_bud_ids": None}
