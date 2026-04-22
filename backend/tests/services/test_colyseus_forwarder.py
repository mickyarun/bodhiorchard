# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the colyseus_forwarder event-bus transport."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.colyseus_forwarder import forward_agent_activity_to_colyseus


async def test_non_matching_topic_does_nothing() -> None:
    with patch(
        "app.services.colyseus_forwarder.publish_to_colyseus",
        new_callable=AsyncMock,
    ) as m:
        await forward_agent_activity_to_colyseus("job:xyz", {"any": "data"})
        m.assert_not_called()


async def test_invalid_org_id_is_logged_and_dropped() -> None:
    with patch(
        "app.services.colyseus_forwarder.publish_to_colyseus",
        new_callable=AsyncMock,
    ) as m:
        await forward_agent_activity_to_colyseus(
            "agent_activity:not-a-uuid",
            {"any": "data"},
        )
        m.assert_not_called()


async def test_valid_topic_forwards_to_colyseus() -> None:
    org_id = uuid.uuid4()
    topic = f"agent_activity:{org_id}"
    payload = {"event_type": "skill_invoked", "skill_slug": "product-manager"}

    with patch(
        "app.services.colyseus_forwarder.publish_to_colyseus",
        new_callable=AsyncMock,
    ) as m:
        await forward_agent_activity_to_colyseus(topic, payload)
        m.assert_awaited_once_with(org_id, "agent_activity", payload)


@pytest.mark.parametrize(
    "topic",
    [
        "agent_activity:",
        "agent_activity:   ",
        "agent_activity",  # missing colon entirely — doesn't even match prefix
    ],
)
async def test_edge_cases_do_not_crash(topic: str) -> None:
    with patch(
        "app.services.colyseus_forwarder.publish_to_colyseus",
        new_callable=AsyncMock,
    ) as m:
        await forward_agent_activity_to_colyseus(topic, {})
        m.assert_not_called()
