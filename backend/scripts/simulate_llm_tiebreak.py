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

"""End-to-end verification: team filter feeds the LLM tiebreak path.

Companion to ``simulate_teams.py``. Sets up the conditions required
for ``smart_assignment.assign_best_for_role`` to invoke the LLM
tiebreak after the team filter narrows the pool, then verifies the
LLM was actually called.

Conditions for the LLM tiebreak (``smart_assignment.py:163-186``):

1. ``len(scored) >= 2`` after team filter + capacity check.
2. ``top_score > _MIN_SCORE_FOR_LLM_TIEBREAK`` (0.3) — i.e. scoring
   used real skill signal, not just workload.
3. ``(top_score - runner_up_score) / top_score < 0.10`` — top two
   within 10% of each other.

The cheapest way to satisfy (2) and (3) is to seed two SkillProfile
rows with similar values for both devs on the same module that
matches the BUD's ``impacted_repos[].repo_name``. Workload is
naturally tied (both fresh devs have 0 active BUDs).

Detection of "LLM actually fired" is multi-signal:
  * The ``method`` recorded on the lifecycle event is ``smart_assignment``.
  * The PATCH-to-development latency exceeds an LLM threshold (raw
    smart scoring is sub-100ms; an LLM subprocess call takes seconds).
  * The picked assignee is one of the two seeded devs (so the
    team filter + smart picker chain produced an answer).

Usage::

    python scripts/simulate_llm_tiebreak.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.bud import BUDTimelineEvent
from app.models.organization import Organization
from app.models.skill_profile import SkillProfile

DEFAULT_BASE = "http://localhost:8000"
ORG_SLUG = "bodhiorchard"
DEFAULT_PASSWORD = "Test@123"
ADMIN_EMAIL = "arun@taskflow.dev"

# Latency above this strongly suggests the LLM subprocess fired.
# Raw smart scoring + DB writes complete well under 500ms on dev.
LLM_LATENCY_THRESHOLD_SECONDS = 1.5


# ---------------------------------------------------------------------
# Live API helpers
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


async def upsert_member(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    *,
    email: str,
    name: str,
    role_id: str,
) -> dict[str, Any]:
    """Create a member if missing, else return the existing row."""
    r = await client.post(
        "/api/v1/members",
        headers=admin,
        json={
            "email": email,
            "name": name,
            "password": DEFAULT_PASSWORD,
            "roleId": role_id,
        },
    )
    if r.status_code == 201:
        return r.json()
    members = (await client.get("/api/v1/members", headers=admin)).json()
    existing = next((m for m in members if m["email"] == email), None)
    if existing is None:
        raise RuntimeError(f"Could not provision {email}: status={r.status_code} body={r.text}")
    return existing


# ---------------------------------------------------------------------
# DB-side seeding (SkillProfile isn't exposed via REST)
# ---------------------------------------------------------------------


async def _org_id(db: AsyncSession) -> uuid.UUID:
    org = (
        await db.execute(select(Organization).where(Organization.slug == ORG_SLUG))
    ).scalar_one()
    return org.id


async def seed_skill_profiles(
    user_ids: list[uuid.UUID], module: str, *, touch_count: int = 40
) -> None:
    """Insert tied SkillProfile rows for each user on ``module``.

    Identical values across users → identical skill component in the
    composite score, plus identical workload (0 active BUDs) → tied
    composite scores → forces the LLM tiebreak gate.
    """
    async with AsyncSessionLocal() as db:
        org_id = await _org_id(db)
        # Clean any leftover rows from prior runs to keep the test
        # deterministic — `(user_id, org_id, module)` is unique.
        for uid in user_ids:
            existing = (
                await db.execute(
                    select(SkillProfile).where(
                        SkillProfile.user_id == uid,
                        SkillProfile.org_id == org_id,
                        SkillProfile.module == module,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                await db.delete(existing)
        await db.flush()

        for uid in user_ids:
            db.add(
                SkillProfile(
                    user_id=uid,
                    org_id=org_id,
                    module=module,
                    skill_score=0.80,
                    touch_count=touch_count,
                    lines_added=touch_count * 10,
                    lines_removed=touch_count * 3,
                    last_touch=datetime.now(UTC),
                )
            )
        await db.commit()


async def cleanup_skill_profiles(user_ids: list[uuid.UUID], module: str) -> None:
    async with AsyncSessionLocal() as db:
        org_id = await _org_id(db)
        for uid in user_ids:
            row = (
                await db.execute(
                    select(SkillProfile).where(
                        SkillProfile.user_id == uid,
                        SkillProfile.org_id == org_id,
                        SkillProfile.module == module,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                await db.delete(row)
        await db.commit()


async def fetch_assigned_event(bud_id: uuid.UUID) -> dict[str, Any] | None:
    """Pull the LAST 'assigned' timeline event for the BUD."""
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(BUDTimelineEvent)
                    .where(
                        BUDTimelineEvent.bud_id == bud_id,
                        BUDTimelineEvent.event_type == "assigned",
                    )
                    .order_by(BUDTimelineEvent.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return None
        return rows[0].detail


# ---------------------------------------------------------------------
# Test orchestration
# ---------------------------------------------------------------------


async def run() -> int:
    suffix = uuid.uuid4().hex[:6]
    print(f"Run suffix: {suffix}")

    # Track everything that needs cleanup in vars so the ``finally``
    # block can tear down even if an assertion or HTTP call raised
    # mid-flight. Without this, a partial run leaks SkillProfile rows
    # and stale teams that pollute the next run.
    team_id: str | None = None
    skill_user_ids: list[uuid.UUID] = []
    module: str | None = None

    async with httpx.AsyncClient(base_url=DEFAULT_BASE, timeout=120.0) as client:
        admin = auth(await login(client, ADMIN_EMAIL, DEFAULT_PASSWORD))

        try:
            # 1. Get a repo to test against.
            repos = (await client.get("/api/v1/settings/repos", headers=admin)).json()
            active_repos = [r for r in repos if r.get("status") == "active"]
            if not active_repos:
                print("FATAL: no active repos in org")
                return 2
            repo = active_repos[0]
            print(f"Using repo: {repo['name']} ({repo['id']})")

            # 2. Resolve the developer role id.
            roles = (await client.get("/api/v1/roles", headers=admin)).json()
            dev_role = next((r for r in roles if r["name"].lower() == "developer"), None)
            if dev_role is None:
                print("FATAL: no developer role")
                return 2

            # 3. Provision two fresh developers (zero BUD load).
            dev_a = await upsert_member(
                client,
                admin,
                email=f"llm-dev-a-{suffix}@taskflow.dev",
                name=f"LLM Dev A {suffix}",
                role_id=dev_role["id"],
            )
            dev_b = await upsert_member(
                client,
                admin,
                email=f"llm-dev-b-{suffix}@taskflow.dev",
                name=f"LLM Dev B {suffix}",
                role_id=dev_role["id"],
            )
            print(f"Provisioned devs: {dev_a['email']} + {dev_b['email']}")

            # 4. Build one team owning the repo with BOTH devs as members.
            team = (
                await client.post(
                    "/api/v1/teams",
                    headers=admin,
                    json={"name": f"LLM Tiebreak Squad {suffix}"},
                )
            ).json()
            team_id = team["id"]
            for d in (dev_a, dev_b):
                await client.post(
                    f"/api/v1/teams/{team_id}/members",
                    headers=admin,
                    json={"user_id": d["id"]},
                )
            await client.post(
                f"/api/v1/teams/{team_id}/repos",
                headers=admin,
                json={"repo_id": repo["id"]},
            )
            print(f"Team built: {team_id} (2 devs, 1 repo)")

            # 5. Seed tied SkillProfile rows so both devs score identically
            #    on this repo's module.
            module = repo["name"].lower()
            skill_user_ids = [uuid.UUID(dev_a["id"]), uuid.UUID(dev_b["id"])]
            await seed_skill_profiles(skill_user_ids, module)
            print(f"Seeded SkillProfiles for module={module!r}")

            # 6. Create a BUD, attach the repo, push to development with timer.
            bud = (
                await client.post(
                    "/api/v1/buds/",
                    headers=admin,
                    json={
                        "title": f"LLM tiebreak BUD {suffix}",
                        "priority": "P1",
                    },
                )
            ).json()
            bud_id = uuid.UUID(bud["id"])
            await client.patch(
                f"/api/v1/buds/{bud_id}",
                headers=admin,
                json={
                    "impacted_repos": [{"repo_id": repo["id"], "repo_name": repo["name"]}],
                },
            )

            print("\nPATCH status=development (this is where LLM should fire)…")
            t0 = time.monotonic()
            r = await client.patch(
                f"/api/v1/buds/{bud_id}",
                headers=admin,
                json={"status": "development"},
            )
            elapsed = time.monotonic() - t0
            print(f"  elapsed: {elapsed:.2f}s   http status: {r.status_code}")

            # 7. Assertions.
            bud_after = r.json()
            assignee_id = bud_after.get("assignee_id")
            assignee_name = bud_after.get("assignee_name")
            winner_email = (
                dev_a["email"]
                if assignee_id == dev_a["id"]
                else dev_b["email"]
                if assignee_id == dev_b["id"]
                else "<other>"
            )
            print(f"  assignee_id={assignee_id} name={assignee_name} ({winner_email})")

            timeline_detail = await fetch_assigned_event(bud_id)
            print(f"  lifecycle event detail: {timeline_detail}")

            # ── Pass / fail summary ─────────────────────────────────────
            passes: list[tuple[str, bool, str]] = []

            passes.append(
                (
                    "assignee landed on one of the seeded devs",
                    assignee_id in (dev_a["id"], dev_b["id"]),
                    f"got {winner_email}",
                )
            )

            passes.append(
                (
                    "lifecycle event recorded with method=smart_assignment",
                    bool(timeline_detail) and timeline_detail.get("method") == "smart_assignment",
                    f"method={(timeline_detail or {}).get('method')}",
                )
            )

            passes.append(
                (
                    "team scope was applied (filter ran)",
                    bool(timeline_detail) and timeline_detail.get("team_scope_applied") is True,
                    f"team_scope_applied={(timeline_detail or {}).get('team_scope_applied')}",
                )
            )

            passes.append(
                (
                    "team scope did NOT fall back (both devs were in the team)",
                    bool(timeline_detail) and timeline_detail.get("team_scope_fell_back") is False,
                    f"team_scope_fell_back={(timeline_detail or {}).get('team_scope_fell_back')}",
                )
            )

            # Latency-based LLM detection. >1.5s strongly implies the
            # Claude subprocess was invoked. Sub-second means scoring went
            # straight to a clear winner without tiebreak.
            passes.append(
                (
                    f"latency > {LLM_LATENCY_THRESHOLD_SECONDS}s (LLM subprocess fingerprint)",
                    elapsed > LLM_LATENCY_THRESHOLD_SECONDS,
                    f"observed {elapsed:.2f}s",
                )
            )

            print("\n--- results ---")
            all_passed = True
            for name, ok, detail in passes:
                mark = "PASS" if ok else "FAIL"
                print(f"  [{mark}] {name} — {detail}")
                if not ok:
                    all_passed = False

            print()
            print("=" * 72)
            if all_passed:
                print("  All assertions passed — team filter → LLM tiebreak chain verified.")
                return 0
            print("  At least one assertion failed (see [FAIL] above).")
            return 1
        finally:
            # Cleanup must run regardless of pass/fail/exception so the
            # next run starts with a clean DB. Each step is wrapped
            # individually so a half-built setup (e.g. team created but
            # SkillProfile seed failed) still gets torn down.
            print("\n--- cleanup ---")
            if skill_user_ids and module:
                try:
                    await cleanup_skill_profiles(skill_user_ids, module)
                except Exception as exc:  # noqa: BLE001 — best-effort cleanup
                    print(f"  WARN: skill profile cleanup failed: {exc}")
            if team_id:
                try:
                    await client.delete(f"/api/v1/teams/{team_id}", headers=admin)
                except Exception as exc:  # noqa: BLE001 — best-effort cleanup
                    print(f"  WARN: team archive failed: {exc}")
            print("  cleanup done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    sys.exit(asyncio.run(run()))
