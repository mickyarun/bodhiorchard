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

"""Unit tests for ``bud_development.on_bud_development_started``.

Pure unit tests with patched collaborators — no DB, no event bus.
We're not testing ``sync_todos_from_tech_spec`` / ``estimate_bud_dates``
themselves (covered by their own suites); we're testing the orchestration
contract: ordering, non-fatality, gated publish.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import bud_development


@pytest.fixture
def fake_bud() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tech_spec_md="## Implementation TODO\n1. Step one\n",
    )


@pytest.fixture
def fake_db() -> MagicMock:
    return MagicMock(name="AsyncSession")


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


class TestOrchestration:
    async def test_happy_path_syncs_publishes_estimates(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        sync = AsyncMock(return_value=3)
        estimate = AsyncMock(return_value={})
        publish = MagicMock()
        monkeypatch.setattr(bud_development, "sync_todos_from_tech_spec", sync)
        monkeypatch.setattr(bud_development, "estimate_bud_dates", estimate)
        monkeypatch.setattr(bud_development, "publish", publish)

        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        sync.assert_awaited_once_with(
            fake_db, org_id, fake_bud.id, fake_bud.tech_spec_md, default_assignee_id=None
        )
        publish.assert_called_once()
        topic, payload = publish.call_args.args
        assert topic == f"todo:{fake_bud.id}"
        assert payload == {
            "event": "todos_regenerated",
            "bud_id": str(fake_bud.id),
            "todo_count": 3,
        }
        estimate.assert_awaited_once()
        assert estimate.await_args.kwargs["trigger"] == "bud_development_started"

    async def test_publish_skipped_when_no_todos_parsed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        monkeypatch.setattr(
            bud_development, "sync_todos_from_tech_spec", AsyncMock(return_value=0)
        )
        monkeypatch.setattr(bud_development, "estimate_bud_dates", AsyncMock(return_value={}))
        publish = MagicMock()
        monkeypatch.setattr(bud_development, "publish", publish)

        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        publish.assert_not_called()

    async def test_todo_sync_failure_is_swallowed_and_estimation_still_runs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        monkeypatch.setattr(
            bud_development,
            "sync_todos_from_tech_spec",
            AsyncMock(side_effect=ValueError("malformed TODO section")),
        )
        estimate = AsyncMock(return_value={})
        publish = MagicMock()
        monkeypatch.setattr(bud_development, "estimate_bud_dates", estimate)
        monkeypatch.setattr(bud_development, "publish", publish)

        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        publish.assert_not_called()
        estimate.assert_awaited_once()

    async def test_estimation_failure_is_swallowed_after_successful_sync(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        monkeypatch.setattr(
            bud_development, "sync_todos_from_tech_spec", AsyncMock(return_value=2)
        )
        monkeypatch.setattr(
            bud_development,
            "estimate_bud_dates",
            AsyncMock(side_effect=RuntimeError("estimator down")),
        )
        publish = MagicMock()
        monkeypatch.setattr(bud_development, "publish", publish)

        # Must not raise.
        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        publish.assert_called_once()

    async def test_actor_metadata_forwarded_to_estimator(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        monkeypatch.setattr(
            bud_development, "sync_todos_from_tech_spec", AsyncMock(return_value=1)
        )
        estimate = AsyncMock(return_value={})
        monkeypatch.setattr(bud_development, "estimate_bud_dates", estimate)
        monkeypatch.setattr(bud_development, "publish", MagicMock())

        actor_id = uuid.uuid4()
        await bud_development.on_bud_development_started(
            fake_db,  # type: ignore[arg-type]
            org_id,
            fake_bud,  # type: ignore[arg-type]
            actor_id=actor_id,
            actor_name="Alice",
        )

        kwargs = estimate.await_args.kwargs
        assert kwargs["actor_id"] == actor_id
        assert kwargs["actor_name"] == "Alice"
