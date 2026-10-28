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

"""Triage session rows and recorders for the triage approval tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1 import triage_sessions as triage_api
from app.models.bud import BUDDocument
from app.models.triage_session import TriageSession, TriageStatus
from app.services import feature_lifecycle
from tests.integration.scan_features_bugs_support import Factory, vec


async def new_session(
    factory: Factory,
    org: uuid.UUID,
    *,
    status: str = TriageStatus.AWAITING_PM,
    priority: str | None = "high",
    name: str = "Saved carts",
    thread: str | None = None,
) -> uuid.UUID:
    """A Slack triage conversation in ``org``, channel C1 (fresh thread unless given)."""
    thread_ts = thread or f"{uuid.uuid4().int % 10**10}.{uuid.uuid4().int % 10**6}"
    async with factory() as db:
        session = TriageSession(
            org_id=org,
            slack_channel="C1",
            thread_ts=thread_ts,
            original_msg_ts=thread_ts,
            requester_slack_id=f"U{uuid.uuid4().hex[:8]}",
            original_text="Can we keep carts between visits?",
            status=status,
            priority=priority,
            feature_name=name,
            triage_context={"problem": "Carts vanish", "users": "Shoppers"},
        )
        db.add(session)
        await db.commit()
        return session.id


@dataclass
class TriageFakes:
    """What reached Slack and the agent trigger.

    Slack posts are ``(token, channel, text marker, thread)``; agent tasks
    are ``(bud, stage, force)``.
    """

    slack: list[tuple[str, str, str, str | None]] = field(default_factory=list)
    agent_tasks: list[tuple[uuid.UUID, str, bool]] = field(default_factory=list)

    @classmethod
    def install(cls, monkeypatch: pytest.MonkeyPatch) -> TriageFakes:
        """Patch the triage module's outside-world calls."""
        fakes = cls()

        async def _post(token: str, channel: str, text: str, **kw: Any) -> dict[str, Any]:
            marker = "BUD-001" if "BUD-001" in text else text[:20]
            fakes.slack.append((token, channel, marker, kw.get("thread_ts")))
            return {"ok": True}

        async def _agent(bud: BUDDocument, stage: str, org: uuid.UUID, db: Any, **kw: Any) -> None:
            fakes.agent_tasks.append((bud.id, stage, bool(kw.get("force"))))

        async def _assign(*args: Any, **kw: Any) -> None:
            return None

        async def _embed(text: str) -> list[float]:
            return vec(1)

        embedder = SimpleNamespace(embed=_embed)
        monkeypatch.setattr(triage_api, "slack_client", SimpleNamespace(chat_post_message=_post))
        monkeypatch.setattr(triage_api, "create_agent_task_for_stage", _agent)
        monkeypatch.setattr(triage_api, "auto_assign_for_phase", _assign)
        monkeypatch.setattr(triage_api, "embedding_service", embedder)
        monkeypatch.setattr(feature_lifecycle, "embedding_service", embedder)
        return fakes
