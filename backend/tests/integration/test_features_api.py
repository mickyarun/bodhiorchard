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

"""The features registry API: view modes, search, repo grouping and org walls."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.scan_features_bugs_support import (
    Factory,
    as_user,
    new_feature,
    new_member,
    new_org,
    new_repo,
)

pytestmark = pytest.mark.integration

FEATURES = "/api/v1/features"


async def _registry(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """An org with a repo holding one active, one retired and one planned feature."""
    org = await new_org(factory)
    repo = await new_repo(factory, org, name="web")
    await new_feature(factory, org, "Checkout flow", repo=repo)
    await new_feature(factory, org, "Legacy cart", repo=repo, active=False)
    await new_feature(
        factory, org, "Feature: Gift cards", source="bud", source_ref="BUD-009",
        feature_status="planned",
    )  # fmt: skip
    headers = as_user(await new_member(factory, org, "developer"), org)
    return org, repo, headers


def _titles(page: dict[str, list[dict[str, str]]]) -> set[str]:
    return {item["featureTitle"] for item in page["items"]}


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("all", {"Checkout flow", "Feature: Gift cards"}),
        ("active", {"Checkout flow"}),
        ("in_progress", {"Feature: Gift cards"}),
        ("deactivated", {"Legacy cart"}),
    ],
)
async def test_each_view_mode_returns_its_slice_with_a_matching_total(
    client: AsyncClient, pg_session_factory: Factory, mode: str, expected: set[str]
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    page = (await client.get(f"{FEATURES}?mode={mode}", headers=headers)).json()
    assert _titles(page) == expected
    assert page["total"] == len(expected)


async def test_search_is_case_insensitive_on_the_title(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    page = (await client.get(f"{FEATURES}?q=  CHECKOUT ", headers=headers)).json()
    blank = (await client.get(f"{FEATURES}?q=%20%20", headers=headers)).json()
    assert _titles(page) == {"Checkout flow"}
    assert blank["total"] == 2


async def test_pagination_keeps_the_full_total(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    first = (await client.get(f"{FEATURES}?limit=1&offset=0", headers=headers)).json()
    rest = (await client.get(f"{FEATURES}?limit=1&offset=1", headers=headers)).json()
    assert first["total"] == rest["total"] == 2
    assert len(first["items"]) == 1 and len(rest["items"]) == 1
    assert _titles(first).isdisjoint(_titles(rest))


async def test_by_repo_groups_primary_features_and_skips_planned_ones(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """``all`` means every active row; the planned BUD row has no repo so it is left out."""
    org, repo, headers = await _registry(pg_session_factory)
    await new_feature(pg_session_factory, org, "Search", repo=repo)
    groups = (await client.get(f"{FEATURES}/by-repo?mode=all", headers=headers)).json()
    retired = (await client.get(f"{FEATURES}/by-repo?mode=deactivated", headers=headers)).json()
    assert len(groups) == 1
    assert groups[0]["repoId"] == str(repo) and groups[0]["repoName"] == "web"
    assert groups[0]["featureCount"] == 2
    assert {f["featureTitle"] for f in groups[0]["features"]} == {"Checkout flow", "Search"}
    assert [f["featureTitle"] for f in retired[0]["features"]] == ["Legacy cart"]


async def test_one_feature_is_returned_even_when_retired(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await new_org(pg_session_factory)
    repo = await new_repo(pg_session_factory, org, name="api")
    feature = await new_feature(pg_session_factory, org, "Old", repo=repo, active=False)
    headers = as_user(await new_member(pg_session_factory, org, "viewer"), org)

    body = (await client.get(f"{FEATURES}/{feature}", headers=headers)).json()

    assert body["isActive"] is False
    assert body["primary"]["repoName"] == "api"


async def test_another_orgs_features_are_invisible(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org_a, repo_a, _ = await _registry(pg_session_factory)
    secret = await new_feature(pg_session_factory, org_a, "Secret", repo=repo_a)
    org_b = await new_org(pg_session_factory)
    outsider = as_user(await new_member(pg_session_factory, org_b, "admin"), org_b)

    single = await client.get(f"{FEATURES}/{secret}", headers=outsider)
    listed = (await client.get(FEATURES, headers=outsider)).json()
    by_repo = (await client.get(f"{FEATURES}/by-repo?repoId={repo_a}", headers=outsider)).json()
    filtered = (await client.get(f"{FEATURES}?repoId={repo_a}", headers=outsider)).json()

    assert single.status_code == 404
    assert listed == {"items": [], "total": 0}
    assert by_repo == []
    assert filtered["total"] == 0


async def test_an_unknown_feature_is_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    assert (await client.get(f"{FEATURES}/{uuid.uuid4()}", headers=headers)).status_code == 404


@pytest.mark.parametrize(
    "query",
    ["?mode=everything", "?limit=0", "?limit=201", "?offset=-1", "?q=" + "x" * 201],
)
async def test_bad_list_parameters_are_rejected(
    client: AsyncClient, pg_session_factory: Factory, query: str
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    assert (await client.get(f"{FEATURES}{query}", headers=headers)).status_code == 422


async def test_match_debug_rejects_an_unknown_match_kind(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, _, headers = await _registry(pg_session_factory)
    bad = await client.get(f"{FEATURES}/match-debug?matchVia=guess", headers=headers)
    good = await client.get(f"{FEATURES}/match-debug?matchVia=cosine", headers=headers)
    assert bad.status_code == 422
    assert good.status_code == 200 and good.json() == []


async def test_features_are_closed_to_members_outside_engineering(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _, _ = await _registry(pg_session_factory)
    hr = as_user(await new_member(pg_session_factory, org, "hr"), org)
    assert (await client.get(FEATURES, headers=hr)).status_code == 403
