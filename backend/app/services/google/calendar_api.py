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
"""The few Google Calendar calls leave sync needs, on a user's primary calendar.

Events carry our own ids and a private tag, so writes are idempotent and
we can find every event we made for a request without storing anything.
"""

from typing import Any

import httpx

BASE = "https://www.googleapis.com/calendar/v3/calendars/primary"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
TAG = "bodhiorchardRequest"
# Out of office and working location aren't returned unless asked for.
_EVENT_TYPES = ("default", "outOfOffice", "workingLocation")
HTTP_TIMEOUT_SECONDS = 15

Event = dict[str, Any]


class CalendarApiError(Exception):
    """Google answered with an error we can't treat as success."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        # Google's own message, e.g. that the Calendar API is disabled in the project.
        self.detail = detail


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        detail = str(response.json().get("error", {}).get("message", ""))
    except ValueError:
        detail = response.text[:200]
    raise CalendarApiError(response.status_code, detail)


async def tagged_event_ids(token: str, tag_value: str) -> set[str]:
    """Ids of live events tagged with ``tag_value`` (one request's events)."""
    ids: set[str] = set()
    params = httpx.QueryParams(
        [
            ("privateExtendedProperty", f"{TAG}={tag_value}"),
            ("maxResults", "250"),
            *(("eventTypes", kind) for kind in _EVENT_TYPES),
        ]
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        page: str | None = None
        while True:
            query = params.add("pageToken", page) if page else params
            response = await client.get(f"{BASE}/events", params=query, headers=_headers(token))
            _raise_for(response)
            body = response.json()
            ids.update(item["id"] for item in body.get("items", []))
            page = body.get("nextPageToken")
            if not page:
                return ids


async def put_event(token: str, event_id: str, body: Event, *, exists: bool) -> None:
    """Create or overwrite the event with our id.

    An id we deleted earlier still exists on Google's side as cancelled, so
    a create that clashes (409) becomes an update that brings it back.
    """
    payload = {**body, "id": event_id, "status": "confirmed"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        if not exists:
            response = await client.post(f"{BASE}/events", json=payload, headers=_headers(token))
            if response.status_code != 409:
                _raise_for(response)
                return
        response = await client.put(
            f"{BASE}/events/{event_id}", json=payload, headers=_headers(token)
        )
        _raise_for(response)


async def delete_event(token: str, event_id: str) -> None:
    """Remove the event; already gone (404 / 410) counts as done."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.delete(f"{BASE}/events/{event_id}", headers=_headers(token))
    if response.status_code in (404, 410):
        return
    _raise_for(response)


async def calendar_name(token: str) -> str:
    """The user's calendar name (usually their email), read the way the sync reads it.

    Uses the events list, which the ``calendar.events`` scope allows; reading
    the calendar itself would need a scope the sync never asks for.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{BASE}/events", params={"maxResults": "1"}, headers=_headers(token)
        )
    _raise_for(response)
    return str(response.json().get("summary", ""))
