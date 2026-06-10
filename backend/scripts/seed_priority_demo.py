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

"""Persistent demo BUDs that exercise every priority + yield-offer surface.

Leaves the following visible on the board so the UI can be inspected:

* 4 BUDs in the bud phase, one at each priority (P0/P1/P2/P3) so the
  card-chip color contract is on screen.
* 5 BUDs in development, distributed so the priority-sort toggle
  visibly reorders them.
* A live pending yield offer for ``alice@taskflow.dev`` so the
  notification bell shows a count and the board notice renders.

Idempotent: discards prior ``[DEMO]`` BUDs before seeding so re-running
keeps the demo set the same size. Run once and explore the UI.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx

API_BASE = "http://localhost:8000/api/v1"
ADMIN_EMAIL = "mickyarunr@gmail.com"
DEV_EMAIL = "alice@taskflow.dev"
PASSWORD = "Test@123"
ORG_SLUG = "bodhiorchard"


async def login(email: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as anon:
        r = await anon.post(
            f"{API_BASE}/auth/login",
            json={"email": email, "password": PASSWORD, "org_slug": ORG_SLUG},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def create_bud(client: httpx.AsyncClient, title: str, priority: str) -> dict:
    r = await client.post(
        f"{API_BASE}/buds/",
        json={"title": title, "priority": priority, "requirements_md": f"Demo ({priority})"},
    )
    r.raise_for_status()
    return r.json()


async def patch_bud(client: httpx.AsyncClient, bud_id: str, **fields) -> dict:
    r = await client.patch(f"{API_BASE}/buds/{bud_id}", json=fields)
    r.raise_for_status()
    return r.json()


async def main() -> None:
    admin_token = await login(ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        # Idempotency — discard prior demo BUDs.
        r = await client.get(f"{API_BASE}/buds/")
        r.raise_for_status()
        prior = [b for b in r.json() if b.get("title", "").startswith("[DEMO]")]
        for b in prior:
            if b["status"] not in ("closed", "discarded"):
                with contextlib.suppress(httpx.HTTPStatusError):
                    await patch_bud(client, b["id"], status="discarded")
        print(f"Pre-flight: discarded {len(prior)} prior [DEMO] BUDs.")

        # ── 1. Four BUDs in bud phase at each priority ────────────
        print("\n[1] Creating BUDs in bud phase at each priority (visible chips):")
        for p in ("P0", "P1", "P2", "P3"):
            b = await create_bud(client, f"[DEMO] {p} backlog item", p)
            print(f"  ✓ BUD-{b['bud_number']} ({p})")

        # ── 2. Five BUDs in development with mixed priorities ─────
        # These exercise the priority sort toggle + the priority chip
        # in the development column. Created in an order that does NOT
        # match priority so the toggle visibly reorders them.
        print("\n[2] Creating development-phase BUDs (mixed priority order):")
        dev_set = [("P2", "demo p2-a"), ("P0", "demo p0-hot"), ("P3", "demo p3-low"),
                   ("P1", "demo p1-high"), ("P2", "demo p2-b")]
        for prio, label in dev_set:
            b = await create_bud(client, f"[DEMO] {label}", prio)
            patched = await patch_bud(client, b["id"], status="development")
            print(
                f"  ✓ BUD-{patched['bud_number']} ({prio}) → "
                f"{patched.get('assignee_name') or '<unassigned>'}"
            )

        # ── 3. Pending yield offer for Alice ──────────────────────
        # Saturate developers so a P0 incoming has nowhere to land,
        # forcing the chain walker into the yield-offer branch. The
        # offer addresses one specific developer — pick a small ramp
        # so we don't drown the board.
        print("\n[3] Raising a yield offer for alice@taskflow.dev:")
        # Each dev's cap is 3. We already created 5 dev BUDs; they'll
        # have distributed across the 5 devs. Top up to full cap.
        # Then a new P0 should produce an offer.
        for i in range(10):  # generous filler so all 5 devs hit cap
            f = await create_bud(client, f"[DEMO] filler {i}", "P3")
            await patch_bud(client, f["id"], status="development")
        incoming = await create_bud(client, "[DEMO] P0 yield trigger", "P0")
        await patch_bud(client, incoming["id"], status="development")
        print(f"  ✓ Incoming BUD-{incoming['bud_number']} (P0) — yield path triggered.")

        # Confirm an offer landed for Alice.
        dev_token = await login(DEV_EMAIL)
        async with httpx.AsyncClient(
            timeout=30.0, headers={"Authorization": f"Bearer {dev_token}"}
        ) as dev_client:
            r = await dev_client.get(f"{API_BASE}/yield-offers")
            r.raise_for_status()
            offers = r.json()
            if offers:
                offer = offers[0]
                print(
                    f"  ✓ Alice sees yield offer: BUD-{offer['incoming_bud_number']} "
                    f"({offer['incoming_bud_priority']}) can replace "
                    f"BUD-{offer['yieldable_bud_number']} ({offer['yieldable_bud_priority']})"
                )
            else:
                print("  ! No offer surfaced — Alice may already be missing from saturation.")

    print("\nDone. Refresh http://localhost:3000/buds to see the demo state.")
    print("Log in as alice@taskflow.dev / Test@123 to see the yield-offer bell + notice.")


if __name__ == "__main__":
    asyncio.run(main())
