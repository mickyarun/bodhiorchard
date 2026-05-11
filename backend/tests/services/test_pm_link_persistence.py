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

"""Unit tests for the PM result handler's link-persistence path.

Both the JSON-fence parser and the persistence wrapper are stubbable
without a real DB: parser is a pure function, the wrapper takes a
session and we monkeypatch the repository constructor.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import agent_result_handlers as handlers
from app.services.agent_result_handlers import (
    _extract_last_json_dict,
    _persist_pm_linked_features,
)

# ── JSON-fence parser ────────────────────────────────────────────


def test_extract_returns_none_when_no_fence() -> None:
    """No code fence → None so callers know to log and bail."""
    assert _extract_last_json_dict("Plain text, no code fence.") is None


def test_extract_returns_dict_from_last_fence() -> None:
    """When multiple fences exist, the LAST one wins (PM appends at end)."""
    output = (
        "```json\n"
        '{"linked_feature_ids": ["a"]}\n'
        "```\n"
        "...later...\n"
        "```json\n"
        '{"linked_feature_ids": ["b"]}\n'
        "```\n"
    )
    parsed = _extract_last_json_dict(output)
    assert parsed == {"linked_feature_ids": ["b"]}


def test_extract_returns_none_when_fence_isnt_object() -> None:
    """A JSON array in the fence is valid JSON but not the contract — drop it."""
    assert _extract_last_json_dict('```json\n["a", "b"]\n```') is None


def test_extract_returns_none_on_malformed_json() -> None:
    """Bad JSON inside the fence is treated as no fence — handler logs and skips."""
    assert _extract_last_json_dict("```json\n{not valid}\n```") is None


# ── Persistence wrapper ─────────────────────────────────────────


async def _noop_record_event(*_args: object, **_kwargs: object) -> None:
    """Stub for ``handlers.record_event`` — drop the call on the floor."""
    return None


class _FakeLinkRepo:
    """Stand-in for :class:`BUDFeatureLinkRepository` that records calls."""

    def __init__(
        self,
        accepted_ids: list[uuid.UUID],
        titles: dict[uuid.UUID, str] | None = None,
    ) -> None:
        self._accepted = accepted_ids
        self._titles = titles or {}
        self.calls: list[tuple[uuid.UUID, list[uuid.UUID], object]] = []

    async def link_features(
        self,
        bud_id: uuid.UUID,
        feature_ids: list[uuid.UUID],
        *,
        source: object,
    ) -> list[uuid.UUID]:
        self.calls.append((bud_id, feature_ids, source))
        return self._accepted

    async def titles_by_ids(self, feature_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        return {fid: self._titles[fid] for fid in feature_ids if fid in self._titles}


@pytest.mark.asyncio
async def test_persist_returns_zero_when_no_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeLinkRepo(accepted_ids=[])
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)
    count = await _persist_pm_linked_features(uuid.uuid4(), uuid.uuid4(), "no fence", None)
    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_persist_returns_zero_when_wrong_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeLinkRepo(accepted_ids=[])
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)
    count = await _persist_pm_linked_features(
        uuid.uuid4(),
        uuid.uuid4(),
        '```json\n{"impacted_repos": ["foo"]}\n```',
        None,
    )
    assert count == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_persist_drops_unparseable_uuids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-UUID entries are dropped; valid ones still reach the repository."""
    good_id = uuid.uuid4()
    fake = _FakeLinkRepo(accepted_ids=[good_id])
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)
    # When any features are accepted, the handler also emits a timeline event;
    # stub it out so this test stays focused on the parse + repo wiring.
    monkeypatch.setattr(handlers, "record_event", _noop_record_event)

    output = f'```json\n{{"linked_feature_ids": ["{good_id}", "not-a-uuid", 42]}}\n```'
    count = await _persist_pm_linked_features(uuid.uuid4(), uuid.uuid4(), output, None)
    assert count == 1
    assert len(fake.calls) == 1
    _bud_id, submitted_ids, _source = fake.calls[0]
    assert submitted_ids == [good_id]


@pytest.mark.asyncio
async def test_persist_emits_timeline_event_when_features_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-links MUST show up in the BUD timeline so users see what the PM did."""
    bud_id = uuid.uuid4()
    org_id = uuid.uuid4()
    good_id = uuid.uuid4()
    fake = _FakeLinkRepo(accepted_ids=[good_id], titles={good_id: "Account Linking"})
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)

    captured: list[dict[str, object]] = []

    async def _capture(
        _db: object,
        passed_org: uuid.UUID,
        passed_bud: uuid.UUID,
        event_type: str,
        actor_id: uuid.UUID | None = None,
        actor_name: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        captured.append(
            {
                "org_id": passed_org,
                "bud_id": passed_bud,
                "event_type": event_type,
                "actor_id": actor_id,
                "actor_name": actor_name,
                "detail": detail,
            }
        )

    monkeypatch.setattr(handlers, "record_event", _capture)

    output = f'```json\n{{"linked_feature_ids": ["{good_id}"]}}\n```'
    count = await _persist_pm_linked_features(bud_id, org_id, output, None)

    assert count == 1
    assert len(captured) == 1
    event = captured[0]
    assert event["event_type"] == "features_auto_linked"
    assert event["bud_id"] == bud_id
    assert event["org_id"] == org_id
    assert event["actor_id"] is None
    assert event["actor_name"] == "PM Agent"
    detail = event["detail"]
    assert isinstance(detail, dict)
    assert detail["count"] == 1
    assert detail["feature_ids"] == [str(good_id)]
    # Title travels with the event so the timeline can name the feature
    # instead of rendering an opaque UUID.
    assert detail["feature_titles"] == ["Account Linking"]


@pytest.mark.asyncio
async def test_persist_skips_timeline_event_when_nothing_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty accepted list (all dupes via ON CONFLICT) means no real activity."""
    fake = _FakeLinkRepo(accepted_ids=[])
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)

    called = False

    async def _flag(*_a: object, **_kw: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(handlers, "record_event", _flag)

    output = f'```json\n{{"linked_feature_ids": ["{uuid.uuid4()}"]}}\n```'
    count = await _persist_pm_linked_features(uuid.uuid4(), uuid.uuid4(), output, None)

    assert count == 0
    assert called is False


@pytest.mark.asyncio
async def test_persist_empty_array_skips_repo_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``{"linked_feature_ids": []}`` is a valid contract — no insert work needed."""
    fake = _FakeLinkRepo(accepted_ids=[])
    monkeypatch.setattr(handlers, "BUDFeatureLinkRepository", lambda *_a, **_kw: fake)
    count = await _persist_pm_linked_features(
        uuid.uuid4(),
        uuid.uuid4(),
        '```json\n{"linked_feature_ids": []}\n```',
        None,
    )
    assert count == 0
    assert fake.calls == []
