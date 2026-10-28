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

"""Install webhooks driving the picker: the App goes from installed-nowhere to listing repos."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.fakes.app_state import EventRecorder
from tests.fakes.github import FakeGitHub
from tests.fakes.github_payloads import installation_event
from tests.fakes.seed import Factory, auth_headers, seed_org
from tests.integration.external_flows.github_support import (
    INSTALLABLE,
    load_org,
    set_installation,
)
from tests.integration.external_flows.webhook_support import deliver, webhook_log

pytestmark = pytest.mark.integration


async def test_an_install_delivery_makes_the_picker_list_the_installed_repos(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, event_recorder: EventRecorder
) -> None:
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)
    await set_installation(app_sessions, org.org_id, None)
    headers = auth_headers(org.owner_id, org.org_id)
    before = (await client.get(INSTALLABLE, headers=headers)).json()

    payload = installation_event("created", gh.app_id, gh.installation_id, "acme/shop-api")
    delivery = f"install-{uuid.uuid4()}"
    resp = await deliver(client, "installation", payload, delivery_id=delivery)
    after = (await client.get(INSTALLABLE, headers=headers)).json()
    await event_recorder.settle()

    assert before["appInstallState"] == "no_install"
    assert resp.status_code == 200
    assert (await load_org(app_sessions, org.org_id)).github_app_installation_id == (
        gh.installation_id
    )
    assert after["appInstallState"] == "ready"
    assert [r["fullName"] for r in after["repos"]] == ["acme/shop-api"]
    assert event_recorder.payloads(f"org:{org.org_id}:install") == [
        {"event_type": "install_set", "status": "ready", "installation_id": gh.installation_id}
    ]
    log = await webhook_log(app_sessions, delivery)
    assert log is not None and log.payload_summary == {
        "app_id": gh.app_id,
        "installation_id": gh.installation_id,
        "action": "created",
    }


@pytest.mark.parametrize("action", ["deleted", "suspend"])
async def test_uninstalling_or_suspending_takes_the_picker_back_to_the_install_step(
    action: str, client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)

    resp = await deliver(
        client, "installation", installation_event(action, gh.app_id, gh.installation_id)
    )
    picker = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert resp.status_code == 200
    assert (await load_org(app_sessions, org.org_id)).github_app_installation_id is None
    assert (picker.json()["appInstallState"], picker.json()["repos"]) == ("no_install", [])
    assert gh.requests == []


async def test_a_reinstall_under_a_new_installation_id_is_followed_by_the_token_exchange(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)
    gh.installation_id += 1  # GitHub issued a new installation

    await deliver(
        client, "installation", installation_event("created", gh.app_id, gh.installation_id)
    )
    picker = await client.get(INSTALLABLE, headers=auth_headers(org.owner_id, org.org_id))

    assert [r["fullName"] for r in picker.json()["repos"]] == ["acme/shop-api"]
    (exchange,) = [r for r in gh.requests if r.url.path.endswith("/access_tokens")]
    assert f"/installations/{gh.installation_id}/" in exchange.url.path


async def test_a_forged_install_delivery_changes_nothing_and_is_not_logged(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions, github=gh)
    payload = installation_event("deleted", gh.app_id, gh.installation_id)
    delivery = f"forged-{uuid.uuid4()}"

    resp = await deliver(
        client, "installation", payload, secret="not-the-secret", delivery_id=delivery
    )

    assert resp.status_code == 401
    assert (await load_org(app_sessions, org.org_id)).github_app_installation_id == (
        gh.installation_id
    )
    assert await webhook_log(app_sessions, delivery) is None


async def test_an_install_delivery_for_an_unknown_app_is_acknowledged_and_ignored(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub
) -> None:
    org = await seed_org(app_sessions, github=gh)
    delivery = f"stray-{uuid.uuid4()}"

    resp = await deliver(
        client,
        "installation",
        installation_event("deleted", gh.app_id + 1, gh.installation_id),
        delivery_id=delivery,
    )

    assert (resp.status_code, resp.text) == (200, "No matching org")
    assert (await load_org(app_sessions, org.org_id)).github_app_installation_id == (
        gh.installation_id
    )
    assert await webhook_log(app_sessions, delivery) is None
