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
 * Matchmaking for the shared rooms. Replays what `joinOrCreate` does against
 * Colyseus's in-memory room cache (LocalDriver): store the listing a room
 * gets on creation, then look up an open room for a later join. The option
 * names are the ones the frontend sends (`ColyseusClient`, `OrgRoomClient`).
 */
import { LocalDriver } from "colyseus"
import { describe, expect, it } from "vitest"
import { roomDefinitions } from "./roomDefinitions"

type SharedRoom = "org" | "coffeebar" | "cafeteria" | "house"

function createListing(driver: LocalDriver, name: SharedRoom, roomId: string, options: object): void {
  driver.persist(
    {
      roomId,
      name,
      clients: 1,
      maxClients: 100,
      locked: false,
      private: false,
      processId: "test",
      ...roomDefinitions[name].getMetadataFromOptions(options),
    } as never,
    true,
  )
}

async function findOpenRoom(
  driver: LocalDriver,
  name: SharedRoom,
  options: object,
): Promise<string | undefined> {
  const found = await driver.findOne({
    locked: false,
    name,
    private: false,
    ...roomDefinitions[name].getFilterOptions(options),
  } as never)
  return found?.roomId
}

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
    createListing(driver, "house", "house-alice", { ownerId: "alice", userId: "bob" })

    expect(await findOpenRoom(driver, "house", { ownerId: "carol", userId: "dan" })).toBeUndefined()
    expect(await findOpenRoom(driver, "house", { ownerId: "alice", userId: "eve" })).toBe(
      "house-alice",
    )
  })

  it("matches on the owning key only, not on per-user options", () => {
    expect(
      roomDefinitions.org.getFilterOptions({ orgId: "org-a", userId: "u1", token: "secret" }),
    ).toEqual({ orgId: "org-a" })
    expect(roomDefinitions.house.getFilterOptions({ ownerId: "alice", name: "Bob" })).toEqual({
      ownerId: "alice",
    })
  })

  it.each(["race", "minigame", "backlash"] as const)(
    "leaves per-match %s rooms unfiltered (they are joined by id)",
    (name) => {
      expect(roomDefinitions[name].getFilterOptions({ orgId: "org-a", userId: "u1" })).toEqual({})
    },
  )
})
