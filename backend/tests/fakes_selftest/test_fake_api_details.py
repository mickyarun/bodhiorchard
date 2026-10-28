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

"""Auth and API details where a lenient fake would hide a real regression."""

from __future__ import annotations

import uuid

import pytest

from app.core.encryption import encrypt_secret
from app.models.organization import Organization
from app.services import slack_client, slack_user_api
from app.services.github_app_auth import (
    discover_installation_id_for_repo,
    get_installation_token,
)
from app.services.github_client import GitHubClient
from tests.fakes.github import FakeGitHub
from tests.fakes.github_keys import new_key_pair
from tests.fakes.slack import FakeSlack


def _org(github: FakeGitHub, private_key_pem: str | None = None) -> Organization:
    org = Organization(id=uuid.uuid4(), name="o", slug="o")
    org.github_app_id = github.app_id
    org.github_app_private_key = encrypt_secret(private_key_pem or github.private_key_pem)
    org.github_app_installation_id = github.installation_id
    org.github_app_slug = github.app_slug
    return org


async def test_jwt_signed_with_a_foreign_key_is_refused(fake_github: FakeGitHub) -> None:
    foreign_private, _ = new_key_pair()

    assert await get_installation_token(_org(fake_github, foreign_private)) is None
    assert fake_github.issued_tokens == []
    assert fake_github.responses == [("/app/installations/4242/access_tokens", 401)]


async def test_repo_installation_lookup_needs_the_app_jwt(fake_github: FakeGitHub) -> None:
    fake_github.add_repo("acme/shop")
    org = _org(fake_github)

    assert await discover_installation_id_for_repo(org, "acme/shop") == fake_github.installation_id
    assert await discover_installation_id_for_repo(org, "acme/missing") is None
    foreign = _org(fake_github, new_key_pair()[0])
    assert await discover_installation_id_for_repo(foreign, "acme/shop") is None


async def test_pull_requests_filter_by_owner_head_and_refuse_duplicates(
    fake_github: FakeGitHub,
) -> None:
    fake_github.add_repo("acme/shop")
    fake_github.extra_tokens.add("pat-1")
    client = GitHubClient("pat-1")

    first = await client.create_pull_request(
        "acme/shop", title="Setup", body="", head="setup", base="main"
    )
    second = await client.create_pull_request(
        "acme/shop", title="Setup", body="", head="setup", base="main"
    )

    assert first is not None and first["number"] == 1
    assert second is None
    assert fake_github.responses[-1] == ("/repos/acme/shop/pulls", 422)
    assert len(await client.list_pull_requests("acme/shop", head="acme:setup")) == 1
    assert await client.list_pull_requests("acme/shop", head="setup") == []


async def test_pr_files_paginate_with_per_page(fake_github: FakeGitHub) -> None:
    fake_github.add_repo("acme/shop")
    fake_github.extra_tokens.add("pat-1")
    fake_github.pr_files[("acme/shop", 3)] = [f"f{i}.py" for i in range(5)]

    files = await GitHubClient("pat-1").list_pr_files("acme/shop", 3)

    assert files == [f"f{i}.py" for i in range(5)]


async def test_slack_refuses_missing_malformed_and_revoked_tokens(fake_slack: FakeSlack) -> None:
    assert await slack_client.chat_post_message("", "C1", "x") is None
    assert await slack_client.chat_post_message("not-a-slack-token", "C1", "x") is None
    await slack_user_api.revoke("xoxp-old")
    assert await slack_client.chat_post_message("xoxp-old", "C1", "x") is None
    assert fake_slack.posted_texts() == ["x", "x", "x"]
    assert fake_slack.threads == {}


async def test_slack_status_is_kept_per_member_token(fake_slack: FakeSlack) -> None:
    away = slack_user_api.SlackStatus(text="On leave", emoji=":palm_tree:", expiration=0)
    await slack_user_api.set_status("xoxp-ada", away)

    assert (await slack_user_api.get_status("xoxp-ada")).text == "On leave"
    assert (await slack_user_api.get_status("xoxp-bob")).text == ""


async def test_slack_oauth_exchange(fake_slack: FakeSlack) -> None:
    grant = await slack_user_api.exchange_code("id", "secret", "good-code", "https://x/cb")

    assert grant.token.startswith("xoxp-")
    with pytest.raises(slack_user_api.SlackUserApiError, match="invalid_code"):
        await slack_user_api.exchange_code("id", "secret", "bad-code", "https://x/cb")


async def test_channel_history_shows_top_level_posts(fake_slack: FakeSlack) -> None:
    posted = await slack_client.chat_post_message("xoxb-1", "C9", "hello")
    assert posted is not None
    await slack_client.chat_post_message("xoxb-1", "C9", "reply", thread_ts=posted["ts"])

    history = await slack_client.conversations_history("xoxb-1", "C9")

    assert [m["text"] for m in history] == ["hello"]
