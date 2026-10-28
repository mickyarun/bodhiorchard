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

"""The Google Calendar client the leave sync uses, against a mocked Google.

The sync only ever lists events carrying our private tag for one request,
so it can't see or remove anything a person put on their own calendar.
"""

import json

import httpx
import pytest
import respx

from app.services.google import calendar_api
from app.services.google.calendar_api import BASE, TAG, CalendarApiError

EVENTS = f"{BASE}/events"


@respx.mock
async def test_listing_asks_only_for_our_tag_and_follows_every_page() -> None:
    pages = respx.get(EVENTS).mock(
        side_effect=[
            httpx.Response(200, json={"items": [{"id": "bo1"}], "nextPageToken": "p2"}),
            httpx.Response(200, json={"items": [{"id": "bo2"}, {"id": "bo1"}]}),
        ]
    )
    assert await calendar_api.tagged_event_ids("tok", "abc123") == {"bo1", "bo2"}
    first, second = (call.request for call in pages.calls)
    assert first.url.params.get_list("privateExtendedProperty") == [f"{TAG}=abc123"]
    # Out of office and working location entries aren't listed unless asked for.
    assert set(first.url.params.get_list("eventTypes")) == {
        "default",
        "outOfOffice",
        "workingLocation",
    }
    assert "pageToken" not in first.url.params
    assert second.url.params["pageToken"] == "p2"
    assert second.url.params.get_list("privateExtendedProperty") == [f"{TAG}=abc123"]
    assert first.headers["Authorization"] == "Bearer tok"


@respx.mock
async def test_a_new_event_is_created_and_a_clashing_id_is_brought_back() -> None:
    create = respx.post(EVENTS).mock(return_value=httpx.Response(409))
    update = respx.put(f"{EVENTS}/boabc").mock(return_value=httpx.Response(200, json={}))
    await calendar_api.put_event("tok", "boabc", {"summary": "Out of office"}, exists=False)
    assert create.called and update.called
    sent = json.loads(update.calls.last.request.content)
    assert sent == {"summary": "Out of office", "id": "boabc", "status": "confirmed"}


@respx.mock
async def test_an_existing_event_is_only_updated() -> None:
    create = respx.post(EVENTS).mock(return_value=httpx.Response(200, json={}))
    update = respx.put(f"{EVENTS}/boabc").mock(return_value=httpx.Response(200, json={}))
    await calendar_api.put_event("tok", "boabc", {}, exists=True)
    assert update.called and not create.called


@respx.mock
async def test_a_created_event_is_not_written_twice() -> None:
    create = respx.post(EVENTS).mock(return_value=httpx.Response(200, json={}))
    update = respx.put(f"{EVENTS}/boabc").mock(return_value=httpx.Response(200, json={}))
    await calendar_api.put_event("tok", "boabc", {}, exists=False)
    assert create.call_count == 1 and not update.called


@pytest.mark.parametrize("status", [200, 204, 404, 410])
@respx.mock
async def test_deleting_something_already_gone_counts_as_done(status: int) -> None:
    gone = respx.delete(f"{EVENTS}/boabc").mock(return_value=httpx.Response(status))
    await calendar_api.delete_event("tok", "boabc")
    assert gone.called


@respx.mock
async def test_errors_carry_googles_message_or_the_start_of_the_body() -> None:
    respx.delete(f"{EVENTS}/boabc").mock(
        return_value=httpx.Response(403, json={"error": {"message": "Calendar API disabled"}})
    )
    with pytest.raises(CalendarApiError) as denied:
        await calendar_api.delete_event("tok", "boabc")
    assert (denied.value.status, denied.value.detail) == (403, "Calendar API disabled")
    respx.get(EVENTS).mock(return_value=httpx.Response(502, text="x" * 500))
    with pytest.raises(CalendarApiError) as broken:
        await calendar_api.tagged_event_ids("tok", "abc")
    assert broken.value.status == 502 and broken.value.detail == "x" * 200


@respx.mock
async def test_a_failed_create_raises_and_never_falls_through_to_an_update() -> None:
    respx.post(EVENTS).mock(
        return_value=httpx.Response(400, json={"error": {"message": "Bad event type"}})
    )
    update = respx.put(f"{EVENTS}/boabc").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(CalendarApiError) as refused:
        await calendar_api.put_event("tok", "boabc", {}, exists=False)
    assert (refused.value.status, refused.value.detail) == (400, "Bad event type")
    assert not update.called


@respx.mock
async def test_a_clash_followed_by_a_failed_update_raises() -> None:
    create = respx.post(EVENTS).mock(return_value=httpx.Response(409))
    respx.put(f"{EVENTS}/boabc").mock(
        return_value=httpx.Response(403, json={"error": {"message": "Forbidden"}})
    )
    with pytest.raises(CalendarApiError) as refused:
        await calendar_api.put_event("tok", "boabc", {}, exists=False)
    assert create.called and (refused.value.status, refused.value.detail) == (403, "Forbidden")
