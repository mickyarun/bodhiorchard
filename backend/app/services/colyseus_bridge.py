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

"""Colyseus bridge — backend → multiplayer server communication.

The Colyseus multiplayer server holds authoritative state for each org's
3D world (members, agents, activity events). This module provides helpers
to push events to that server whenever something relevant happens in
the backend (dev activity, agent activity, member presence changes).

Authentication: shared secret in the `X-Bridge-Secret` header, verified
on the Colyseus side before accepting the event.

Communication is fire-and-forget HTTP — the backend does not block on
Colyseus responses. If the Colyseus server is down, events are dropped
silently (clients will see the world "freeze" until the server is back).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Shared async HTTP client with a short timeout — bridge calls should
# never block the request path for long.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=2.0)
    return _client


async def publish_to_colyseus(
    org_id: uuid.UUID | str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Publish an event to the Colyseus OrgRoom for the given org.

    Fire-and-forget: failures are logged but never raised. The backend
    continues normally even if Colyseus is unreachable.

    Args:
        org_id: The org whose OrgRoom should receive the event.
        event_type: Event name (e.g., "dev_activity", "agent_activity").
        data: Event payload. Must be JSON-serializable.
    """
    url = f"{settings.colyseus.url}/internal/publish"
    payload = {
        "orgId": str(org_id),
        "type": event_type,
        "data": data,
    }
    headers = {
        "X-Bridge-Secret": settings.colyseus.bridge_secret,
        "Content-Type": "application/json",
    }

    try:
        client = _get_client()
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            logger.warning(
                "colyseus_bridge_publish_failed",
                status=response.status_code,
                event_type=event_type,
                org_id=str(org_id),
            )
    except httpx.HTTPError as err:
        logger.warning(
            "colyseus_bridge_unreachable",
            error=str(err),
            event_type=event_type,
            org_id=str(org_id),
        )
    except asyncio.CancelledError:
        raise
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "colyseus_bridge_unexpected_error",
            error=str(err),
            event_type=event_type,
        )


async def close_client() -> None:
    """Close the shared HTTP client. Called on app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
