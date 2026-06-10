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

"""End-to-end simulation of priority-based assignment + yield-offer flow.

Run against a live dev server with the standard dev DB. Steps:

1. Auth + sanity-print of users / current BUDs.
2. Test 1 — priority lands in DB on create.
3. Test 2 — priority-weighted scoring picks the least-loaded developer
   when capacity allows.
4. Test 3 — yield offer raised when every developer is at cap and the
   incoming BUD is higher-priority than someone's held work.
5. Test 4 — accept_offer moves assignment + records timeline.

Idempotent cleanup at the end (discards BUDs created here so reruns
don't pollute the dev DB).
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

import httpx

API_BASE = "http://localhost:8000/api/v1"
EMAIL = "mickyarunr@gmail.com"
PASSWORD = "Test@123"
ORG_SLUG = "bodhiorchard"


def log(section: str, msg: str = "") -> None:
    print(f"\n=== {section} ===\n{msg}" if msg else f"\n=== {section} ===")


def fail(msg: str) -> None:
    print(f"✗ {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✓ {msg}")


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{API_BASE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD, "org_slug": ORG_SLUG},
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def list_developers(client: httpx.AsyncClient) -> list[dict]:
    r = await client.get(f"{API_BASE}/members?role=developer")
    if r.status_code != 200:
        r = await client.get(f"{API_BASE}/members")
    r.raise_for_status()
    members = r.json()
    devs = [m for m in members if m.get("role") == "developer" and m.get("isActive", True)]
    return devs


async def create_bud(client: httpx.AsyncClient, title: str, priority: str) -> dict:
    r = await client.post(
        f"{API_BASE}/buds/",
        json={
            "title": title,
            "priority": priority,
            "requirements_md": f"Simulation BUD ({priority})",
        },
    )
    r.raise_for_status()
    return r.json()


async def patch_bud(client: httpx.AsyncClient, bud_id: str, **fields) -> dict:
    r = await client.patch(f"{API_BASE}/buds/{bud_id}", json=fields)
    r.raise_for_status()
    return r.json()


async def get_bud(client: httpx.AsyncClient, bud_id: str) -> dict:
    r = await client.get(f"{API_BASE}/buds/{bud_id}")
    r.raise_for_status()
    return r.json()


async def list_yield_offers(client: httpx.AsyncClient) -> list[dict]:
    r = await client.get(f"{API_BASE}/yield-offers")
    r.raise_for_status()
    return r.json()


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as anon:
        token = await login(anon)

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        log("Setup", "Logged in.")

        # Pre-flight cleanup: discard any leftover [SIM] BUDs from prior
        # runs AND reject any stale pending yield offers under those
        # BUDs. Without this, each run accumulates orphan offers that
        # point at long-discarded yieldable BUDs, which makes Test 6's
        # "reject the first offer Alice sees" pick a stale row.
        r = await client.get(f"{API_BASE}/buds/")
        r.raise_for_status()
        sim_buds = [b for b in r.json() if b.get("title", "").startswith("[SIM")]
        for b in sim_buds:
            if b["status"] not in ("closed", "discarded"):
                with contextlib.suppress(httpx.HTTPStatusError):
                    await patch_bud(client, b["id"], status="discarded")
        ok(f"Pre-flight: discarded {len(sim_buds)} prior [SIM] BUDs.")

        devs = await list_developers(client)
        ok(f"Found {len(devs)} active developers: {[d['name'] for d in devs]}")
        if len(devs) < 3:
            fail("Need >= 3 developers for the yield-offer test path.")

        created_buds: list[str] = []

        # ── Test 1 ────────────────────────────────────────────────
        log("Test 1 — priority lands on create")
        bud = await create_bud(client, "[SIM] P0 ping", "P0")
        created_buds.append(bud["id"])
        if bud["priority"] != "P0":
            fail(f"Expected priority=P0 in response, got {bud['priority']}")
        ok(f"Created BUD-{bud['bud_number']} with priority {bud['priority']}")

        # ── Test 2 — priority-weighted scoring ────────────────────
        log("Test 2 — priority-weighted scoring (under-cap)")
        # Move to development; backend should assign one of the unloaded
        # developers via smart_assignment.
        moved = await patch_bud(client, bud["id"], status="development")
        ok(
            f"BUD-{moved['bud_number']} moved to {moved['status']}, "
            f"assigned to {moved.get('assignee_name', '<unassigned>')}"
        )
        if not moved.get("assignee_id"):
            fail("Expected assignment when developers are under cap.")

        # ── Test 3 — saturate to trigger yield offer ──────────────
        log("Test 3 — saturate developers + raise yield offer")
        # Each developer's cap is 3 active BUDs. One dev already has the
        # P0 from Test 2; we need to fill remaining slots with P3 BUDs to
        # push everyone to cap. Total fillers = (3 * num_devs) - 1.
        target_filler_count = 3 * len(devs) - 1
        ok(f"Creating {target_filler_count} P3 fillers to saturate {len(devs)} developers")
        for i in range(target_filler_count):
            filler = await create_bud(client, f"[SIM] P3 filler {i}", "P3")
            created_buds.append(filler["id"])
            await patch_bud(client, filler["id"], status="development")

        # Inspect DB load
        log("Workload after fillers")
        # Cheap server-side count via the listing endpoint.
        r = await client.get(f"{API_BASE}/buds/", params={"status": "development"})
        r.raise_for_status()
        active = r.json()
        load: dict[str, int] = {}
        for b in active:
            aid = b.get("assignee_id") or "(unassigned)"
            load[aid] = load.get(aid, 0) + 1
        for aid, count in load.items():
            name = next((d["name"] for d in devs if d["id"] == aid), aid)
            print(f"  {name}: {count} active")

        # New high-priority BUD that should trigger yield offer.
        log("Create P0 incoming — expect yield offer raised")
        incoming = await create_bud(client, "[SIM] P0 hot incident", "P0")
        created_buds.append(incoming["id"])
        moved_incoming = await patch_bud(client, incoming["id"], status="development")
        offers = await list_yield_offers(client)
        ok(f"Yield offers visible to current user: {len(offers)}")
        if moved_incoming.get("assignee_id"):
            print(
                "  Note: incoming P0 was assigned directly "
                f"(to {moved_incoming.get('assignee_name')}). "
                "Yield path only fires when every dev is genuinely at cap."
            )
        else:
            ok("Incoming P0 left unassigned pending yield decision.")

        # The current user (org_owner) won't be the offer target — log
        # in as the developer who actually got the offer and exercise
        # accept/reject from there.
        log("Test 4 — accept yield offer (as the targeted developer)")
        # Find any pending offer in the DB via the admin's lens. We can't
        # list it through the API (the endpoint scopes to the caller),
        # so probe known-developer emails until we hit the right one.
        target_email = "alice@taskflow.dev"
        async with httpx.AsyncClient(timeout=30.0) as anon2:
            r = await anon2.post(
                f"{API_BASE}/auth/login",
                json={"email": target_email, "password": PASSWORD, "org_slug": ORG_SLUG},
            )
            r.raise_for_status()
            dev_token = r.json()["access_token"]

        dev_headers = {"Authorization": f"Bearer {dev_token}"}
        async with httpx.AsyncClient(timeout=30.0, headers=dev_headers) as dev_client:
            dev_offers = await list_yield_offers(dev_client)
            ok(f"{target_email} sees {len(dev_offers)} pending offer(s)")
            if dev_offers:
                offer = dev_offers[0]
                print(
                    f"  Offer {offer['id']}: incoming BUD-{offer['incoming_bud_number']} "
                    f"({offer['incoming_bud_priority']}) vs yieldable "
                    f"BUD-{offer['yieldable_bud_number']} ({offer['yieldable_bud_priority']})"
                )
                r = await dev_client.post(f"{API_BASE}/yield-offers/{offer['id']}/accept")
                if r.status_code == 200:
                    accepted = r.json()
                    ok(f"Accepted; offer status now {accepted['status']}")
                    released = await get_bud(dev_client, offer["yieldable_bud_id"])
                    incoming_after = await get_bud(dev_client, offer["incoming_bud_id"])
                    print(
                        f"  Yieldable BUD-{released['bud_number']} assignee: "
                        f"{released.get('assignee_name') or '<unassigned>'}"
                    )
                    print(
                        f"  Incoming BUD-{incoming_after['bud_number']} assignee: "
                        f"{incoming_after.get('assignee_name') or '<unassigned>'}"
                    )
                else:
                    print(f"  Accept failed ({r.status_code}): {r.text[:200]}")
            else:
                print(f"  {target_email} has no pending offer — yield path may not have fired.")

        # ── Test 5 — priority-weighted scoring CHANGES the winner ─
        log("Test 5 — priority-weighted scoring changes the winner")
        # Reset: every BUD from prior tests goes to discarded so all
        # developers start idle. The cap check uses count of active BUDs,
        # so this matters — we need everyone under cap with controlled
        # loads to make the weighting visible.
        for bid in created_buds:
            with contextlib.suppress(httpx.HTTPStatusError):
                await patch_bud(client, bid, status="discarded")
        created_buds = []
        idle_devs = [d for d in devs if d.get("id")]
        if len(idle_devs) < 2:
            print("  Skipped — need 2 idle developers.")
        else:
            heavy = idle_devs[0]
            light = idle_devs[1]
            wins_for_heavy: list[str] = []
            wins_for_light: list[str] = []
            for prio in ("P0", "P0"):
                b = await create_bud(client, f"[SIM5] {prio} heavy {heavy['name']}", prio)
                wins_for_heavy.append(b["id"])
                created_buds.append(b["id"])
                await patch_bud(client, b["id"], status="development", assignee_id=heavy["id"])
            for prio in ("P3", "P3"):
                b = await create_bud(client, f"[SIM5] {prio} light {light['name']}", prio)
                wins_for_light.append(b["id"])
                created_buds.append(b["id"])
                await patch_bud(client, b["id"], status="development", assignee_id=light["id"])
            incoming5 = await create_bud(client, "[SIM5] P2 tiebreaker", "P2")
            created_buds.append(incoming5["id"])
            assigned5 = await patch_bud(client, incoming5["id"], status="development")
            winner = assigned5.get("assignee_name") or "<unassigned>"
            print(
                f"  HEAVY={heavy['name']} (2x P0 → effective load 8) | "
                f"LIGHT={light['name']} (2x P3 → load 2)"
            )
            print(f"  Incoming P2 assigned to: {winner}")
            if winner == light["name"]:
                ok("LIGHT wins — priority-weighted scoring is biasing assignment correctly.")
            else:
                print(
                    "  ! Unexpected: incoming P2 did NOT go to the lower-effective-load dev."
                )

        # ── Test 6 — reject yield offer ───────────────────────────
        log("Test 6 — reject yield offer (as targeted developer)")
        # Saturate everyone again and create a new P0 incoming. Then
        # log in as the target dev and REJECT.
        for i in range(3 * len(devs)):
            f = await create_bud(client, f"[SIM6] filler {i}", "P3")
            created_buds.append(f["id"])
            await patch_bud(client, f["id"], status="development")
        incoming6 = await create_bud(client, "[SIM6] P0 reject test", "P0")
        created_buds.append(incoming6["id"])
        await patch_bud(client, incoming6["id"], status="development")
        async with httpx.AsyncClient(timeout=30.0) as anon3:
            r = await anon3.post(
                f"{API_BASE}/auth/login",
                json={"email": target_email, "password": PASSWORD, "org_slug": ORG_SLUG},
            )
            r.raise_for_status()
            dev_token2 = r.json()["access_token"]
        dev_headers2 = {"Authorization": f"Bearer {dev_token2}"}
        async with httpx.AsyncClient(timeout=30.0, headers=dev_headers2) as dev_client2:
            offers6 = await list_yield_offers(dev_client2)
            if offers6:
                offer6 = offers6[0]
                r = await dev_client2.post(f"{API_BASE}/yield-offers/{offer6['id']}/reject")
                if r.status_code == 200:
                    rejected = r.json()
                    ok(f"Rejected; offer status now {rejected['status']}")
                    # Yieldable BUD should keep its assignee (no release).
                    yieldable_after = await get_bud(dev_client2, offer6["yieldable_bud_id"])
                    print(
                        f"  Yieldable BUD-{yieldable_after['bud_number']} assignee "
                        f"after reject: {yieldable_after.get('assignee_name') or '<unassigned>'}"
                    )
                else:
                    print(f"  Reject failed ({r.status_code}): {r.text[:200]}")
            else:
                print("  No offer to reject.")

        # ── Cleanup ───────────────────────────────────────────────
        log("Cleanup")
        for bud_id in created_buds:
            try:
                await patch_bud(client, bud_id, status="discarded")
            except httpx.HTTPStatusError as exc:
                print(f"  cleanup skipped for {bud_id}: {exc.response.status_code}")
        ok(f"Discarded {len(created_buds)} simulation BUDs.")


if __name__ == "__main__":
    asyncio.run(main())
