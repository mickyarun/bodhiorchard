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
 * Join checks for the house, coffee bar and cafeteria rooms. Each attack
 * replays the real sequence: matchmaking picks an open room from the join
 * options, then that room's onAuth runs with the same options.
 */
import { LocalDriver, type Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createListing, findOpenRoom, type SharedRoom } from "../testing/matchmaking"
import { CafeteriaRoom } from "./CafeteriaRoom"
import { CoffeeBarRoom } from "./CoffeeBarRoom"
import { HouseRoom } from "./HouseRoom"

type InteriorRoom = HouseRoom | CoffeeBarRoom | CafeteriaRoom
type InteriorName = Extract<SharedRoom, "house" | "coffeebar" | "cafeteria">

const ROOMS: Record<InteriorName, () => InteriorRoom> = {
  house: () => new HouseRoom(),
  coffeebar: () => new CoffeeBarRoom(),
  cafeteria: () => new CafeteriaRoom(),
}
const ORG_A_ROOM = { orgId: "org-a", ownerId: "alice" }
const NAMES = Object.keys(ROOMS) as InteriorName[]

const fetchMock = vi.fn()
const created: InteriorRoom[] = []

/** Make the backend verify every token as `userId` in `orgId`. */
function verifiedAs(userId: string, orgId: string, name: string): void {
  fetchMock.mockImplementation(async () =>
    Response.json({ valid: true, user_id: userId, org_id: orgId, name }),
  )
}

function createRoom(name: InteriorName, options: object): InteriorRoom {
  const room = ROOMS[name]()
  created.push(room)
  room.onCreate(options)
  return room
}

function fakeClient(): Client {
  return { sessionId: "s1", userData: undefined, send: vi.fn() } as unknown as Client
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  for (const room of created) {
    room.setSimulationInterval()
    room.clock.clear()
  }
  created.length = 0
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe.each(NAMES)("%s room join", (name) => {
  it("refuses to create a room without its org", () => {
    expect(() => createRoom(name, { ownerId: "alice" })).toThrow("room needs its orgId")
  })

  it("takes the player from the verified token, not the join options", async () => {
    verifiedAs("ana", "org-a", "Ana")
    const room = createRoom(name, ORG_A_ROOM)
    const client = fakeClient()
    const raw = { orgId: "org-a", userId: "alice", name: "Alice", token: "ana-jwt" }

    room.onJoin(client, raw, await room.onAuth(client, raw))

    expect(room.state.players.get("s1")).toMatchObject({ userId: "ana", name: "Ana" })
  })

  it("keeps a client that leaves out orgId out of another org's room", async () => {
    const driver = new LocalDriver()
    createListing(driver, name, "room-a", ORG_A_ROOM)
    const room = createRoom(name, ORG_A_ROOM)
    verifiedAs("mallory", "org-b", "Mallory")
    const raw = { ownerId: "alice", token: "mallory-jwt" }

    expect(await findOpenRoom(driver, name, raw)).toBe("room-a")
    await expect(room.onAuth(fakeClient(), raw)).rejects.toThrow("token org mismatch")
  })

  it("keeps a client that forges another org's orgId out of that org's room", async () => {
    const driver = new LocalDriver()
    createListing(driver, name, "room-a", ORG_A_ROOM)
    const room = createRoom(name, ORG_A_ROOM)
    verifiedAs("mallory", "org-b", "Mallory")
    const raw = { orgId: "org-a", ownerId: "alice", userId: "alice", token: "mallory-jwt" }

    expect(await findOpenRoom(driver, name, raw)).toBe("room-a")
    await expect(room.onAuth(fakeClient(), raw)).rejects.toThrow("token org mismatch")
  })

  it("refuses a tokenless join unless the operator opted in", async () => {
    const room = createRoom(name, ORG_A_ROOM)

    await expect(
      room.onAuth(fakeClient(), { orgId: "org-a", userId: "alice", name: "Alice" }),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("refuses an onJoin that did not pass onAuth", () => {
    const room = createRoom(name, ORG_A_ROOM)

    expect(() => room.onJoin(fakeClient(), { userId: "alice" })).toThrow("join was not verified")
  })
})

describe("house room creation", () => {
  it("refuses to create a house room without its owner", () => {
    expect(() => createRoom("house", { orgId: "org-a" })).toThrow("room needs its ownerId")
  })
})
