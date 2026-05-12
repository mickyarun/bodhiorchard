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

The hook is a thin enqueuer: build the ``TodoGenerateJobPayload``,
call ``create_job(JOB_TODO_GENERATE, ...)``, return. All Claude work
runs in the worker. These tests verify the enqueue contract and the
non-fatal failure path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import bud_development


@pytest.fixture
def fake_bud() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), tech_spec_md="## Plan\n")


@pytest.fixture
def fake_db() -> MagicMock:
    return MagicMock(name="AsyncSession")


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


class TestEnqueue:
    async def test_enqueues_initial_job_with_correct_payload(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        create_job = MagicMock(return_value=SimpleNamespace(job_id="job-1"))
        monkeypatch.setattr(bud_development, "create_job", create_job)

        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        create_job.assert_called_once()
        kwargs = create_job.call_args.kwargs
        assert kwargs["payload"]["bud_id"] == str(fake_bud.id)
        assert kwargs["payload"]["org_id"] == str(org_id)
        assert kwargs["payload"]["mode"] == "initial"

    async def test_actor_metadata_forwarded_to_payload(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        create_job = MagicMock(return_value=SimpleNamespace(job_id="j"))
        monkeypatch.setattr(bud_development, "create_job", create_job)

        actor_id = uuid.uuid4()
        await bud_development.on_bud_development_started(
            fake_db,  # type: ignore[arg-type]
            org_id,
            fake_bud,
            actor_id=actor_id,
            actor_name="Alice",
        )

        payload = create_job.call_args.kwargs["payload"]
        assert payload["actor_id"] == str(actor_id)
        assert payload["actor_name"] == "Alice"

    async def test_enqueue_failure_publishes_failed_and_does_not_raise(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_db: MagicMock,
        fake_bud: SimpleNamespace,
        org_id: uuid.UUID,
    ) -> None:
        monkeypatch.setattr(
            bud_development,
            "create_job",
            MagicMock(side_effect=RuntimeError("queue full")),
        )
        publish = MagicMock()
        monkeypatch.setattr(bud_development, "publish", publish)

        # Must not raise — caller's transaction stays intact.
        await bud_development.on_bud_development_started(fake_db, org_id, fake_bud)  # type: ignore[arg-type]

        publish.assert_called_once_with(
            f"todo:{fake_bud.id}",
            {"event": "generating_failed", "error": "queue full"},
        )
