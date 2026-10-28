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

"""The Slack events route: what it refuses, and what it acknowledges but ignores."""

from __future__ import annotations

import json
import time

import pytest
from httpx import AsyncClient

from app.services.job_queue import JOB_FEATURE_QA, JOB_TRIAGE
from app.services.slack_verify import MAX_AGE_SECONDS
from tests.fakes.seed import SLACK_SIGNING_SECRET, Factory
from tests.fakes.signing import signed_slack_event
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import InlineJobs
from tests.integration.external_flows.slack_support import (
    EVENTS,
    post_event,
    reaction,
    say_in_channel,
    triage_org,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("forgery", ["wrong_secret", "stale_timestamp", "unknown_team"])
async def test_unverifiable_events_are_refused_and_start_nothing(
    forgery: str,
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    triage_jobs: InlineJobs,
) -> None:
    await triage_org(app_sessions, slack)
    ts = say_in_channel(slack, "UREQ", "Please add dark mode")
    secret, timestamp, team = SLACK_SIGNING_SECRET, None, None
    if forgery == "wrong_secret":
        secret = "0" * 32
    elif forgery == "stale_timestamp":
        timestamp = int(time.time()) - MAX_AGE_SECONDS - 60
    else:
        team = "TNOBODY00"

    event = reaction("UREQ", "brain", ts)
    resp = await post_event(client, slack, event, secret=secret, timestamp=timestamp, team_id=team)

    assert resp.status_code == 401
    assert (triage_jobs.queued(JOB_TRIAGE), triage_jobs.queued(JOB_FEATURE_QA)) == (0, 0)
    assert slack.calls == []


async def test_unsigned_url_verification_echoes_the_challenge(client: AsyncClient) -> None:
    body = json.dumps({"type": "url_verification", "challenge": "c-123"})

    resp = await client.post(EVENTS, content=body, headers={"Content-Type": "application/json"})

    assert (resp.status_code, resp.text) == (200, "c-123")


async def test_slack_retries_are_acknowledged_without_reprocessing(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack, triage_jobs: InlineJobs
) -> None:
    await triage_org(app_sessions, slack)
    ts = say_in_channel(slack, "UREQ", "Please add dark mode")

    body, headers = signed_slack_event("x", slack.team_id, reaction("UREQ", "brain", ts))
    resp = await client.post(EVENTS, content=body, headers={**headers, "X-Slack-Retry-Num": "1"})

    assert resp.status_code == 200
    assert triage_jobs.queued(JOB_TRIAGE) == 0


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "reaction_added",
            "user": "UREQ",
            "reaction": "thumbsup",
            "item": {"type": "message", "channel": "C0PRODUCT", "ts": "1.0"},
        },
        {
            "type": "reaction_added",
            "user": "UREQ",
            "reaction": "brain",
            "item": {"type": "file", "channel": "C0PRODUCT", "ts": "1.0"},
        },
        {
            "type": "message",
            "bot_id": "B1",
            "text": "beep",
            "ts": "2.0",
            "thread_ts": "1.0",
            "channel": "C0PRODUCT",
        },
        {
            "type": "message",
            "user": "UREQ",
            "text": "top level",
            "ts": "3.0",
            "channel": "C0PRODUCT",
        },
    ],
    ids=["other_emoji", "reaction_on_a_file", "bot_reply", "top_level_message"],
)
async def test_events_that_are_not_intake_are_acknowledged_and_ignored(
    event: dict[str, object],
    client: AsyncClient,
    app_sessions: Factory,
    slack: FakeSlack,
    triage_jobs: InlineJobs,
) -> None:
    await triage_org(app_sessions, slack)

    assert (await post_event(client, slack, event)).status_code == 200
    assert (triage_jobs.queued(JOB_TRIAGE), triage_jobs.queued(JOB_FEATURE_QA)) == (0, 0)
