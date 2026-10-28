// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Matchmaking for the shared rooms. The option names are the ones the
 * frontend sends (`ColyseusClient`, `OrgRoomClient`).
 */
import { LocalDriver, Room } from "colyseus"
import { describe, expect, it } from "vitest"
import { authenticateJoin } from "./auth/roomAuth"
import { roomDefinitions } from "./roomDefinitions"
import { createListing, findOpenRoom } from "./testing/matchmaking"

describe("shared room matchmaking", () => {
  it.each(["org", "coffeebar", "cafeteria"] as const)(
    "sends a second org's %s join to its own room, not the first org's",
    async (name) => {
      const driver = new LocalDriver()
      createListing(driver, name, "room-a", { orgId: "org-a", userId: "alice", token: "t" })

      expect(await findOpenRoom(driver, name, { orgId: "org-b", userId: "bob" })).toBeUndefined()
      expect(await findOpenRoom(driver, name, { orgId: "org-a", userId: "ana" })).toBe("room-a")
    },
  )

  it("keeps visitors of different houses in different rooms", async () => {
    const driver = new LocalDriver()
    createListing(driver, "house", "house-alice", { orgId: "org-a", ownerId: "alice" })

    expect(
      await findOpenRoom(driver, "house", { orgId: "org-a", ownerId: "carol" }),
    ).toBeUndefined()
    expect(await findOpenRoom(driver, "house", { orgId: "org-a", ownerId: "alice" })).toBe(
      "house-alice",
    )
  })

  it("keeps the same owner's house apart across orgs", async () => {
    const driver = new LocalDriver()
    createListing(driver, "house", "house-a-alice", { orgId: "org-a", ownerId: "alice" })

    expect(
      await findOpenRoom(driver, "house", { orgId: "org-b", ownerId: "alice" }),
    ).toBeUndefined()
  })

  // The filter routes, it does not guard: a key the client leaves out matches
  // any value. That is why every join must name its org and is verified for
  // it before matchmaking (see rooms/PreMatchmakingAuth.test.ts).
  it.each(["org", "coffeebar", "cafeteria"] as const)(
    "matches a %s join that leaves out orgId to whichever org's room is open",
    async (name) => {
      const driver = new LocalDriver()
      createListing(driver, name, "room-a", { orgId: "org-a" })

      expect(await findOpenRoom(driver, name, { userId: "mallory", token: "t" })).toBe("room-a")
    },
  )

  it("matches a house join that leaves out orgId to any org's house of that owner", async () => {
    const driver = new LocalDriver()
    createListing(driver, "house", "house-a-alice", { orgId: "org-a", ownerId: "alice" })

    expect(await findOpenRoom(driver, "house", { ownerId: "alice", token: "t" })).toBe(
      "house-a-alice",
    )
  })

  it("matches on the owning key only, not on per-user options", () => {
    expect(
      roomDefinitions.org.getFilterOptions({ orgId: "org-a", userId: "u1", token: "secret" }),
    ).toEqual({ orgId: "org-a" })
    expect(
      roomDefinitions.house.getFilterOptions({ orgId: "org-a", ownerId: "alice", name: "Bob" }),
    ).toEqual({ orgId: "org-a", ownerId: "alice" })
  })

  it.each(["race", "minigame", "backlash"] as const)(
    "leaves per-match %s rooms unfiltered (they are joined by id)",
    (name) => {
      expect(roomDefinitions[name].getFilterOptions({ orgId: "org-a", userId: "u1" })).toEqual({})
    },
  )
})

describe("join checks for every registered room", () => {
  // Colyseus runs the static onAuth inside the matchmaker, before it creates
  // a room or reserves a seat; an instance onAuth would run only at
  // WebSocket connect, after the seat is held (see auth/roomAuth.ts).
  it.each(Object.entries(roomDefinitions))(
    "%s verifies the join before matchmaking and has no instance onAuth",
    (_name, handler) => {
      const klass = handler.klass as unknown as typeof Room
      expect(klass.onAuth).toBe(authenticateJoin)
      expect(klass.prototype.onAuth).toBe(Room.prototype.onAuth)
    },
  )
})
