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

"""FakeGitHub, FakeSlack and FakeJira answering the app's real HTTP clients."""

from __future__ import annotations

import uuid

import pytest

from app.core.encryption import encrypt_secret
from app.models.organization import Organization
from app.services import slack_client, slack_interactive
from app.services.github_app_auth import get_installation_token
from app.services.github_client import GitHubClient
from app.services.github_install_repos import list_remote_branches_via_api
from app.services.jira_client import JiraApiError, JiraClient
from tests.fakes.github import FakeGitHub
from tests.fakes.jira import FakeJira, jira_issue
from tests.fakes.slack import FakeSlack


def _app_org(github: FakeGitHub, *, installation_id: int | None = None) -> Organization:
    org = Organization(id=uuid.uuid4(), name="o", slug="o")
    org.github_app_id = github.app_id
    org.github_app_private_key = encrypt_secret(github.private_key_pem)
    org.github_app_installation_id = installation_id or github.installation_id
    org.github_app_slug = github.app_slug
    return org


async def test_installation_token_is_exchanged_once_and_cached(fake_github: FakeGitHub) -> None:
    org = _app_org(fake_github)

    first = await get_installation_token(org)
    second = await get_installation_token(org)

    assert first == second == "ghs_fake0001"
    assert fake_github.issued_tokens == ["ghs_fake0001"]


async def test_unknown_installation_yields_no_token(fake_github: FakeGitHub) -> None:
    assert await get_installation_token(_app_org(fake_github, installation_id=999)) is None


async def test_jwt_signed_with_another_key_is_refused(fake_github: FakeGitHub) -> None:
    other = FakeGitHub(app_id=fake_github.app_id + 1)
    org = _app_org(fake_github)
    org.github_app_id = other.app_id

    assert await get_installation_token(org) is None
    assert fake_github.issued_tokens == []


async def test_branches_follow_link_pagination(fake_github: FakeGitHub) -> None:
    fake_github.add_repo("acme/shop", "main", "develop", "release", "hotfix")
    fake_github.max_page_size = 2

    branches = await list_remote_branches_via_api(_app_org(fake_github), "acme/shop")

    assert branches == ["main", "develop", "release", "hotfix"]
    pages = [r.url.params.get("page") for r in fake_github.requests if "branches" in r.url.path]
    assert pages == [None, "2"]


async def test_rate_limit_401_and_404_reach_the_client(fake_github: FakeGitHub) -> None:
    fake_github.add_repo("acme/shop")
    fake_github.extra_tokens.add("pat-1")
    fake_github.pr_files[("acme/shop", 5)] = ["a.py"]
    client = GitHubClient("pat-1")
    fake_github.rate_limit("GET", r"/pulls/5/files$")

    assert await client.list_pr_files("acme/shop", 5) == []
    assert await client.list_pr_files("acme/shop", 5) == ["a.py"]
    assert await client.list_pr_files("acme/missing", 5) == []
    assert await GitHubClient("revoked").list_pr_files("acme/shop", 5) == []
    assert [status for _, status in fake_github.responses] == [403, 200, 404, 401]


async def test_slack_posts_are_recorded_and_threaded(fake_slack: FakeSlack) -> None:
    first = await slack_client.chat_post_message("xoxb-1", "C1", "hello")
    assert first is not None
    await slack_client.chat_post_message("xoxb-1", "C1", "reply", thread_ts=first["ts"])

    assert fake_slack.posted_texts() == ["hello", "reply"]
    assert fake_slack.calls_to("chat.postMessage")[1].args["thread_ts"] == first["ts"]
    assert {c.token for c in fake_slack.calls} == {"xoxb-1"}
    replies = await slack_client.conversations_replies("xoxb-1", "C1", first["ts"])
    assert [m["text"] for m in replies] == ["hello", "reply"]


async def test_slack_errors_and_rate_limits(fake_slack: FakeSlack) -> None:
    fake_slack.add_user("U1", "Ada", "ada@example.test")
    fake_slack.fail("users.info", "missing_scope")
    fake_slack.rate_limit("chat.postMessage")

    assert await slack_client.users_info("xoxb-1", "U1") is None
    assert (await slack_client.users_info("xoxb-1", "U1") or {})["real_name"] == "Ada"
    outcome = await slack_client.post_message_outcome("xoxb-1", "C1", "hi")
    assert (outcome.ok, outcome.error) == (False, "ratelimited")
    _, _, error = await slack_interactive.post_message("xoxb-1", "C1", "hi")
    assert error == ""


async def test_jira_search_pages_through_every_issue(fake_jira: FakeJira) -> None:
    for n in range(1, 4):
        fake_jira.add_issue(jira_issue(f"SHOP-{n}", f"Story {n}"))
    fake_jira.add_issue(jira_issue("OTHER-1", "Elsewhere"))

    async with JiraClient(fake_jira.site_url, fake_jira.email, fake_jira.api_token) as client:
        assert await client.get_site_identifier() == fake_jira.site_url
        pages = [page async for page in client.search_issues("project = SHOP")]

    assert [[i["key"] for i in page] for page in pages] == [["SHOP-1", "SHOP-2"], ["SHOP-3"]]


async def test_jira_bad_credentials_raise(fake_jira: FakeJira) -> None:
    async with JiraClient(fake_jira.site_url, fake_jira.email, "wrong") as client:
        with pytest.raises(JiraApiError):
            await client.test_connection()


async def test_jira_rate_limit_is_retried(fake_jira: FakeJira) -> None:
    fake_jira.fail(r"/serverInfo$", 429)

    async with JiraClient(fake_jira.site_url, fake_jira.email, fake_jira.api_token) as client:
        info = await client.test_connection()

    assert info["serverTitle"] == "Fake Jira"
    assert len(fake_jira.requests) == 2
