#!/usr/bin/env python3
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

"""End-to-end simulation for the Teams feature against a running backend.

Exercises every documented happy path, validation rejection, and
corner case from the implementation plan. Designed to be re-runnable:
creates teams with a unique suffix, cleans them up (archives) at the
end. Reports a tabulated pass/fail summary so regressions on the live
API surface are obvious.

Usage::

    python scripts/simulate_teams.py [--base-url URL] [--password PWD]

Defaults:
    base-url     http://localhost:8000
    password     Test@123  (matches scripts/seed_priority_demo.py)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE = "http://localhost:8000"
ORG_SLUG = "bodhiorchard"
DEFAULT_PASSWORD = "Test@123"

ADMIN_EMAIL = "arun@taskflow.dev"
QA_EMAIL = "alice@taskflow.dev"  # qa role — used for permission-denial tests


# ---------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------


@dataclass
class TestResult:
    name: str
    kind: str  # "positive" | "negative" | "corner"
    passed: bool
    detail: str = ""


@dataclass
class Suite:
    results: list[TestResult] = field(default_factory=list)

    def record(
        self,
        name: str,
        kind: str,
        passed: bool,
        detail: str = "",
    ) -> bool:
        self.results.append(TestResult(name, kind, passed, detail))
        glyph = "PASS" if passed else "FAIL"
        print(f"  [{glyph}] {name}{(' — ' + detail) if detail else ''}")
        return passed

    def summary(self) -> int:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print()
        print("=" * 72)
        print(f"  {passed}/{total} passed   ({failed} failed)")
        print("=" * 72)
        if failed > 0:
            print()
            print("Failed cases:")
            for r in self.results:
                if not r.passed:
                    print(f"  - [{r.kind}] {r.name}: {r.detail}")
        return 0 if failed == 0 else 1


# ---------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "org_slug": ORG_SLUG},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def get_seed_data(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pull the active member + repo lists so the simulation can pick real IDs."""
    members = (await client.get("/api/v1/members", headers=admin_headers)).json()
    repos = (await client.get("/api/v1/settings/repos", headers=admin_headers)).json()
    active_members = [m for m in members if m.get("isActive")]
    active_repos = [r for r in repos if r.get("status") == "active"]
    return active_members, active_repos


# ---------------------------------------------------------------------
# Scenario blocks
# ---------------------------------------------------------------------


async def run_positive(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    seed_suffix: str,
    members: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> tuple[str, str]:
    """Returns (primary_team_id, secondary_team_id) for later cleanup + cases."""
    print("\n--- positive cases ---")

    # Pick non-admin members so we don't fight with the org_owner.
    pickable = [m for m in members if m["email"] != ADMIN_EMAIL]
    assert len(pickable) >= 3, "Seed has fewer than 3 non-admin members"
    assert len(repos) >= 2, "Seed has fewer than 2 active repos"

    primary_name = f"Sim Payments {seed_suffix}"
    secondary_name = f"Sim Platform {seed_suffix}"

    # P1: create team
    r = await client.post(
        "/api/v1/teams",
        headers=admin,
        json={"name": primary_name, "description": "Initial description"},
    )
    suite.record(
        "create team (201)",
        "positive",
        r.status_code == 201,
        f"status={r.status_code}",
    )
    primary = r.json()
    primary_id = primary["id"]

    # P2: list teams shows it
    listed = (await client.get("/api/v1/teams", headers=admin)).json()
    suite.record(
        "list_teams shows new team",
        "positive",
        any(t["id"] == primary_id for t in listed),
    )

    # P3: GET single team returns description + empty members/repos
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "GET team has description, empty members/repos",
        "positive",
        detail["description"] == "Initial description"
        and detail["members"] == []
        and detail["repos"] == [],
    )

    # P4: PATCH name + description
    r = await client.patch(
        f"/api/v1/teams/{primary_id}",
        headers=admin,
        json={"name": primary_name + " v2", "description": "Updated desc"},
    )
    suite.record(
        "PATCH name + description",
        "positive",
        r.status_code == 200
        and r.json()["name"] == primary_name + " v2"
        and r.json()["description"] == "Updated desc",
    )

    # P5: add 3 members
    for m in pickable[:3]:
        r = await client.post(
            f"/api/v1/teams/{primary_id}/members",
            headers=admin,
            json={"user_id": m["id"]},
        )
        if r.status_code != 201:
            suite.record(
                f"add member {m['email']}",
                "positive",
                False,
                f"status={r.status_code} body={r.text[:120]}",
            )
            break
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "team has 3 members after bulk add",
        "positive",
        len(detail["members"]) == 3,
        f"got {len(detail['members'])}",
    )

    # P6: add 2 repos
    for repo in repos[:2]:
        r = await client.post(
            f"/api/v1/teams/{primary_id}/repos",
            headers=admin,
            json={"repo_id": repo["id"]},
        )
        if r.status_code != 201:
            suite.record(
                f"add repo {repo['name']}",
                "positive",
                False,
                f"status={r.status_code} body={r.text[:120]}",
            )
            break
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "team has 2 repos after bulk add",
        "positive",
        len(detail["repos"]) == 2,
    )

    # P7: remove one member, count drops by 1
    target_member = pickable[0]["id"]
    r = await client.delete(
        f"/api/v1/teams/{primary_id}/members/{target_member}",
        headers=admin,
    )
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "remove member drops count",
        "positive",
        r.status_code == 204 and len(detail["members"]) == 2,
    )

    # P8: remove one repo
    target_repo = repos[0]["id"]
    r = await client.delete(
        f"/api/v1/teams/{primary_id}/repos/{target_repo}",
        headers=admin,
    )
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "remove repo drops count",
        "positive",
        r.status_code == 204 and len(detail["repos"]) == 1,
    )

    # P9: create a second team (used by many-to-many tests + assignment integration)
    r = await client.post("/api/v1/teams", headers=admin, json={"name": secondary_name})
    secondary_id = r.json()["id"]
    suite.record("create second team", "positive", r.status_code == 201)

    return primary_id, secondary_id


async def run_validation_and_404(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    primary_id: str,
    pickable: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> None:
    print("\n--- negative cases: validation + 404 ---")

    # N1: empty name → 422 (Pydantic min_length=1)
    r = await client.post("/api/v1/teams", headers=admin, json={"name": ""})
    suite.record("empty name → 422", "negative", r.status_code == 422, f"got {r.status_code}")

    # N2: duplicate name → 409
    dup_name = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()["name"]
    r = await client.post("/api/v1/teams", headers=admin, json={"name": dup_name})
    suite.record(
        "duplicate name → 409",
        "negative",
        r.status_code == 409,
        f"got {r.status_code} body={r.text[:120]}",
    )

    # N3: GET unknown team → 404
    r = await client.get(f"/api/v1/teams/{uuid.uuid4()}", headers=admin)
    suite.record("GET unknown team → 404", "negative", r.status_code == 404)

    # N4: PATCH unknown team → 404
    r = await client.patch(
        f"/api/v1/teams/{uuid.uuid4()}", headers=admin, json={"name": "anything"}
    )
    suite.record("PATCH unknown team → 404", "negative", r.status_code == 404)

    # N5: DELETE (archive) unknown team → 404
    r = await client.delete(f"/api/v1/teams/{uuid.uuid4()}", headers=admin)
    suite.record(
        "archive unknown team → 404",
        "negative",
        r.status_code == 404,
        f"got {r.status_code}",
    )

    # N6: add cross-org user (random UUID — definitely not in org_to_user)
    r = await client.post(
        f"/api/v1/teams/{primary_id}/members",
        headers=admin,
        json={"user_id": str(uuid.uuid4())},
    )
    suite.record(
        "add cross-org user → 400 (composite-FK reject)",
        "negative",
        r.status_code == 400,
        f"got {r.status_code} body={r.text[:120]}",
    )

    # N7: add cross-org repo
    r = await client.post(
        f"/api/v1/teams/{primary_id}/repos",
        headers=admin,
        json={"repo_id": str(uuid.uuid4())},
    )
    suite.record(
        "add cross-org repo → 400 (composite-FK reject)",
        "negative",
        r.status_code == 400,
    )

    # N8: add member twice (unique constraint)
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    if detail["members"]:
        existing_user = detail["members"][0]["user_id"]
        r = await client.post(
            f"/api/v1/teams/{primary_id}/members",
            headers=admin,
            json={"user_id": existing_user},
        )
        suite.record(
            "add same member twice → 400",
            "negative",
            r.status_code == 400,
            f"got {r.status_code}",
        )

    # N9: add same repo twice
    if detail["repos"]:
        existing_repo = detail["repos"][0]["repo_id"]
        r = await client.post(
            f"/api/v1/teams/{primary_id}/repos",
            headers=admin,
            json={"repo_id": existing_repo},
        )
        suite.record(
            "add same repo twice → 400",
            "negative",
            r.status_code == 400,
            f"got {r.status_code}",
        )

    # N10: remove non-member → 404
    r = await client.delete(
        f"/api/v1/teams/{primary_id}/members/{uuid.uuid4()}",
        headers=admin,
    )
    suite.record("remove non-member → 404", "negative", r.status_code == 404)

    # N11: remove unmapped repo → 404
    r = await client.delete(
        f"/api/v1/teams/{primary_id}/repos/{uuid.uuid4()}",
        headers=admin,
    )
    suite.record("remove unmapped repo → 404", "negative", r.status_code == 404)


async def run_permission_checks(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    qa: dict[str, str],
    suite: Suite,
    seed_suffix: str,
) -> None:
    print("\n--- negative cases: permission gates ---")

    # QA role does NOT have team:manage. Verify each mutation 403s.
    r = await client.post(
        "/api/v1/teams", headers=qa, json={"name": f"Sim QA-attempt {seed_suffix}"}
    )
    suite.record(
        "qa user cannot create team (403)",
        "negative",
        r.status_code == 403,
        f"got {r.status_code}",
    )

    # QA can list (team:view is part of the qa role bundle in seed perms;
    # confirm via the call).
    r = await client.get("/api/v1/teams", headers=qa)
    suite.record(
        "qa user can list teams (200 or 403 — report observed)",
        "positive" if r.status_code == 200 else "negative",
        r.status_code in (200, 403),
        f"observed status={r.status_code} (200=team:view granted, 403=not)",
    )


async def run_corner_cases(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    primary_id: str,
    secondary_id: str,
    pickable: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> None:
    print("\n--- corner cases ---")

    # C1: many-to-many — map the SAME repo to both teams
    shared_repo = repos[1]["id"]
    r = await client.post(
        f"/api/v1/teams/{secondary_id}/repos",
        headers=admin,
        json={"repo_id": shared_repo},
    )
    suite.record(
        "same repo on two teams (many-to-many)",
        "corner",
        r.status_code == 201,
        f"got {r.status_code}",
    )

    # C2: user in multiple teams
    multi_user = pickable[1]["id"]
    r = await client.post(
        f"/api/v1/teams/{secondary_id}/members",
        headers=admin,
        json={"user_id": multi_user},
    )
    suite.record(
        "same user on two teams",
        "corner",
        r.status_code == 201,
        f"got {r.status_code}",
    )

    # C3: description clearing — PATCH null clears
    r = await client.patch(
        f"/api/v1/teams/{primary_id}",
        headers=admin,
        json={"description": None},
    )
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "PATCH description=null clears it",
        "corner",
        r.status_code == 200 and detail["description"] is None,
        f"description={detail['description']!r}",
    )

    # C4: description preservation — PATCH another field WITHOUT description
    # should keep the prior value
    await client.patch(
        f"/api/v1/teams/{primary_id}",
        headers=admin,
        json={"description": "Will be preserved"},
    )
    r = await client.patch(
        f"/api/v1/teams/{primary_id}",
        headers=admin,
        json={
            "name": (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()["name"]
        },
    )
    detail = (await client.get(f"/api/v1/teams/{primary_id}", headers=admin)).json()
    suite.record(
        "PATCH without description preserves prior value",
        "corner",
        detail["description"] == "Will be preserved",
        f"description={detail['description']!r}",
    )

    # C5: archive then list with include_archived=false → not visible
    await client.delete(f"/api/v1/teams/{secondary_id}", headers=admin)
    active_only = (await client.get("/api/v1/teams", headers=admin)).json()
    suite.record(
        "archived team excluded from default list",
        "corner",
        not any(t["id"] == secondary_id for t in active_only),
    )

    # C6: include_archived=true shows it again with status=archived
    all_teams = (await client.get("/api/v1/teams?include_archived=true", headers=admin)).json()
    archived_entry = next((t for t in all_teams if t["id"] == secondary_id), None)
    suite.record(
        "include_archived=true surfaces archived team with status=archived",
        "corner",
        archived_entry is not None and archived_entry["status"] == "archived",
        f"entry={archived_entry}",
    )

    # C7: restore via PATCH status=active
    r = await client.patch(
        f"/api/v1/teams/{secondary_id}",
        headers=admin,
        json={"status": "active"},
    )
    suite.record(
        "restore archived team via PATCH status=active",
        "corner",
        r.status_code == 200 and r.json()["status"] == "active",
        f"status_in_body={r.json().get('status')}",
    )

    # C8: archived team is excluded from team-scope assignment filter
    # Verify by archiving secondary again, then checking that
    # list_member_ids_for_repos (called internally) wouldn't pick it.
    # We can't hit the internal helper via REST; instead, archive and
    # confirm the team's repos still appear on the archived team's
    # detail (data integrity) but the team is excluded from active list.
    await client.delete(f"/api/v1/teams/{secondary_id}", headers=admin)
    archived_detail = (await client.get(f"/api/v1/teams/{secondary_id}", headers=admin)).json()
    suite.record(
        "archived team retains its members + repos rows (no cascade delete)",
        "corner",
        archived_detail["status"] == "archived"
        and len(archived_detail["repos"]) > 0
        and len(archived_detail["members"]) > 0,
        f"members={len(archived_detail['members'])} repos={len(archived_detail['repos'])}",
    )

    # C9: name too long (>255) → 422
    r = await client.post(
        "/api/v1/teams",
        headers=admin,
        json={"name": "X" * 256},
    )
    suite.record("name > 255 chars → 422", "negative", r.status_code == 422)

    # C10: legacy redirect — /settings/teams should NOT respond on the API
    # router (that's a frontend-only route). Just sanity-check no team
    # endpoint accidentally lives there.
    r = await client.get("/api/v1/settings/teams", headers=admin)
    suite.record(
        "no /api/v1/settings/teams API leak",
        "corner",
        r.status_code == 404,
        f"got {r.status_code}",
    )


async def _ensure_fresh_dev(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    *,
    email: str,
    name: str,
    developer_role_id: str,
    suffix: str,
) -> dict[str, Any] | None:
    """Create a fresh developer with zero active BUD load.

    Idempotent: if the user already exists from a prior simulation run
    we just refetch them. Returns the member dict or None on failure.
    The assignment integration block needs developers that aren't at
    the per-role active-BUD cap, otherwise auto_assign_for_phase
    correctly returns ``all_at_capacity`` and the BUD stays unassigned.
    """
    r = await client.post(
        "/api/v1/members",
        headers=admin,
        json={
            "email": email,
            "name": name,
            "password": DEFAULT_PASSWORD,
            "roleId": developer_role_id,
        },
    )
    if r.status_code == 201:
        return r.json()
    if r.status_code == 409:
        # Pre-existing from a prior run — fetch them from the members list.
        all_members = (await client.get("/api/v1/members", headers=admin)).json()
        existing = next((m for m in all_members if m["email"] == email), None)
        return existing
    suite.record(
        f"provision fresh dev {email}",
        "positive",
        False,
        f"status={r.status_code} body={r.text[:160]}",
    )
    return None


async def run_assignment_integration(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    seed_suffix: str,
    members: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> list[str]:
    """End-to-end: team narrows the assignee pool when a BUD has impacted_repos.

    Builds two isolated teams:
      * Squad-A owns repo X with developer ``dev_a`` only.
      * Squad-B owns repo Y with developer ``dev_b`` only.
    Then creates two BUDs, transitions each to DEVELOPMENT, and
    asserts the assignee landed on the right developer. Also exercises
    the fall-back path: a BUD whose impacted_repo is owned by no team
    should still get an assignee (org-wide fallback) and the lifecycle
    event should carry ``team_scope_fell_back``.

    Returns the team IDs it created so the caller can clean them up.
    """
    print("\n--- assignment integration ---")
    if len(repos) < 3:
        suite.record(
            "assignment integration prerequisites",
            "positive",
            False,
            f"need >=3 repos ({len(repos)})",
        )
        return []

    # Provision fresh devs with zero active-BUD load. The seed
    # developers (bob/dave/carol/arun) are typically at the per-role
    # cap from prior demos; auto_assign would correctly report
    # ``all_at_capacity`` against them and prove nothing about the team
    # filter. Two fresh users with no BUD history side-step that.
    roles = (await client.get("/api/v1/roles", headers=admin)).json()
    dev_role = next(
        (r for r in roles if r["name"].lower() == "developer"),
        None,
    )
    if dev_role is None:
        suite.record(
            "developer role lookup",
            "positive",
            False,
            "no role named 'developer' in /v1/roles",
        )
        return []
    dev_a = await _ensure_fresh_dev(
        client,
        admin,
        suite,
        email=f"sim-dev-a-{seed_suffix}@taskflow.dev",
        name=f"Sim Dev A {seed_suffix}",
        developer_role_id=dev_role["id"],
        suffix=seed_suffix,
    )
    dev_b = await _ensure_fresh_dev(
        client,
        admin,
        suite,
        email=f"sim-dev-b-{seed_suffix}@taskflow.dev",
        name=f"Sim Dev B {seed_suffix}",
        developer_role_id=dev_role["id"],
        suffix=seed_suffix,
    )
    if not dev_a or not dev_b:
        return []

    repo_owned_a, repo_owned_b, repo_unowned = repos[0], repos[1], repos[2]

    # Build Squad-A (owns repo_a, has dev_a only).
    r = await client.post(
        "/api/v1/teams",
        headers=admin,
        json={"name": f"Sim Squad-A {seed_suffix}"},
    )
    squad_a = r.json()["id"]
    await client.post(
        f"/api/v1/teams/{squad_a}/members",
        headers=admin,
        json={"user_id": dev_a["id"]},
    )
    await client.post(
        f"/api/v1/teams/{squad_a}/repos",
        headers=admin,
        json={"repo_id": repo_owned_a["id"]},
    )

    # Build Squad-B (owns repo_b, has dev_b only).
    r = await client.post(
        "/api/v1/teams",
        headers=admin,
        json={"name": f"Sim Squad-B {seed_suffix}"},
    )
    squad_b = r.json()["id"]
    await client.post(
        f"/api/v1/teams/{squad_b}/members",
        headers=admin,
        json={"user_id": dev_b["id"]},
    )
    await client.post(
        f"/api/v1/teams/{squad_b}/repos",
        headers=admin,
        json={"repo_id": repo_owned_b["id"]},
    )

    async def _bud_for(repo: dict[str, Any], priority: str = "P1") -> dict[str, Any]:
        """Create a BUD, set impacted_repos, push to DEVELOPMENT."""
        r = await client.post(
            "/api/v1/buds/",
            headers=admin,
            json={
                "title": f"Sim BUD {seed_suffix} → {repo['name']}",
                "priority": priority,
            },
        )
        r.raise_for_status()
        bud = r.json()
        # Set impacted_repos (editable post-creation per BUDUpdate).
        await client.patch(
            f"/api/v1/buds/{bud['id']}",
            headers=admin,
            json={
                "impacted_repos": [{"repo_id": repo["id"], "repo_name": repo["name"]}],
            },
        )
        # Walk to DEVELOPMENT so the dev-role chain fires.
        await client.patch(
            f"/api/v1/buds/{bud['id']}",
            headers=admin,
            json={"status": "development"},
        )
        # Re-read for assignee.
        return (await client.get(f"/api/v1/buds/{bud['id']}", headers=admin)).json()

    # Case A: BUD on Squad-A's repo → dev_a should win.
    bud_a = await _bud_for(repo_owned_a)
    suite.record(
        f"BUD on Squad-A repo assigned to dev_a ({dev_a['email']})",
        "positive",
        bud_a.get("assignee_id") == dev_a["id"],
        f"assignee={bud_a.get('assignee_name')} (expected {dev_a['name']})",
    )

    # Case B: BUD on Squad-B's repo → dev_b should win, NOT dev_a
    bud_b = await _bud_for(repo_owned_b)
    suite.record(
        f"BUD on Squad-B repo assigned to dev_b ({dev_b['email']})",
        "positive",
        bud_b.get("assignee_id") == dev_b["id"],
        f"assignee={bud_b.get('assignee_name')} (expected {dev_b['name']})",
    )

    # Case C: BUD on an UNOWNED repo → should fall back to org-wide
    # (i.e. SOME developer gets it; we can't assert which, but it must
    # not be None — fall-back should not leave the BUD unassigned).
    bud_c = await _bud_for(repo_unowned)
    suite.record(
        "BUD on unowned repo falls back to org-wide (assignee non-null)",
        "corner",
        bud_c.get("assignee_id") is not None,
        f"assignee={bud_c.get('assignee_name')}",
    )

    # Case D: cross-isolation — Squad-A's BUD assignee must NOT be dev_b
    # even though dev_b is in Squad-B and active.
    suite.record(
        "Squad-A BUD does NOT bleed into Squad-B's dev",
        "corner",
        bud_a.get("assignee_id") != dev_b["id"],
    )

    return [squad_a, squad_b]


async def cleanup(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    suite: Suite,
    team_ids: list[str],
) -> None:
    print("\n--- cleanup (archive sim teams) ---")
    for tid in team_ids:
        r = await client.delete(f"/api/v1/teams/{tid}", headers=admin)
        if r.status_code not in (204, 404):
            suite.record(
                f"cleanup archive {tid}",
                "positive",
                False,
                f"status={r.status_code}",
            )
    print("  cleanup done.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


async def main(base_url: str, password: str) -> int:
    suite = Suite()
    seed_suffix = uuid.uuid4().hex[:6]

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Sanity: backend is up
        try:
            admin_token = await login(client, ADMIN_EMAIL, password)
        except httpx.HTTPStatusError as exc:
            print(f"FATAL: admin login failed — {exc.response.text}")
            return 2
        except httpx.RequestError as exc:
            print(f"FATAL: cannot reach {base_url} — {exc}")
            return 2

        admin = auth(admin_token)
        try:
            qa_token = await login(client, QA_EMAIL, password)
        except httpx.HTTPStatusError:
            print(f"WARN: qa login ({QA_EMAIL}) failed — permission tests will be skipped")
            qa_token = ""
        qa = auth(qa_token) if qa_token else {}

        active_members, active_repos = await get_seed_data(client, admin)
        print(f"Seed: {len(active_members)} active members, {len(active_repos)} active repos.")
        if len(active_members) < 4 or len(active_repos) < 2:
            print(
                "FATAL: need >=4 active members and >=2 active repos in the org. "
                "Run scripts/seed_priority_demo.py first."
            )
            return 2
        pickable = [m for m in active_members if m["email"] != ADMIN_EMAIL]

        primary_id, secondary_id = await run_positive(
            client, admin, suite, seed_suffix, active_members, active_repos
        )

        await run_validation_and_404(client, admin, suite, primary_id, pickable, active_repos)

        if qa:
            await run_permission_checks(client, admin, qa, suite, seed_suffix)
        else:
            suite.record(
                "permission tests SKIPPED (qa login failed)",
                "negative",
                False,
                "no qa token",
            )

        await run_corner_cases(
            client, admin, suite, primary_id, secondary_id, pickable, active_repos
        )

        integration_team_ids = await run_assignment_integration(
            client, admin, suite, seed_suffix, active_members, active_repos
        )

        await cleanup(client, admin, suite, [primary_id, secondary_id, *integration_team_ids])

    return suite.summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.base_url, args.password)))
