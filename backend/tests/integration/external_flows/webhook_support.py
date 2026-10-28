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

"""Signed GitHub deliveries and the rows they leave behind."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient, Response

from app.models.bud import BUDDocument, BUDStatus
from app.models.pull_request import PullRequest
from app.models.webhook_log import WebhookLog
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.pull_request import PullRequestRepository
from app.repositories.webhook_log import WebhookLogRepository
from tests.fakes.seed import WEBHOOK_SECRET, Factory
from tests.fakes.signing import signed_github_webhook

WEBHOOK_URL = "/api/v1/webhooks/github"


async def deliver(
    client: AsyncClient,
    event: str,
    payload: dict[str, Any],
    *,
    secret: str = WEBHOOK_SECRET,
    delivery_id: str | None = None,
) -> Response:
    """POST one signed delivery to the webhook route."""
    body, headers = signed_github_webhook(secret, event, payload, delivery_id)
    return await client.post(WEBHOOK_URL, content=body, headers=headers)


async def add_bud(
    factory: Factory, org_id: uuid.UUID, title: str, status: BUDStatus = BUDStatus.DEVELOPMENT
) -> tuple[uuid.UUID, int]:
    """A BUD in ``status``; returns ``(id, number)``."""
    async with factory() as db:
        repo = BUDRepository(db, org_id=org_id)
        number = await repo.next_bud_number()
        bud = await repo.create(
            BUDDocument(org_id=org_id, bud_number=number, title=title, status=status)
        )
        await db.commit()
        return bud.id, number


async def timeline_details(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID, event_type: str
) -> list[dict[str, Any]]:
    """``detail`` of each ``event_type`` timeline event on the BUD."""
    async with factory() as db:
        events = await BUDTimelineRepository(db, org_id=org_id).list_for_bud_by_event_type(
            bud_id, event_type
        )
        return [dict(e.detail or {}) for e in events]


async def pull_request(factory: Factory, org_id: uuid.UUID, github_pr_id: int) -> PullRequest:
    """The tracked PR row for GitHub's PR id."""
    async with factory() as db:
        row = await PullRequestRepository(db, org_id=org_id).get_by_github_pr_id(github_pr_id)
        assert row is not None, f"PR {github_pr_id} is not tracked"
        return row


async def webhook_log(factory: Factory, delivery_id: str) -> WebhookLog | None:
    """The ledger row for a delivery, if one was written."""
    async with factory() as db:
        return await WebhookLogRepository(db).find_by_delivery_id(delivery_id)
