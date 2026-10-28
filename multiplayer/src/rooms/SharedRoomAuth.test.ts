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
 * replays the real sequence: the static onAuth checks the join options before
 * matchmaking, matchmaking picks an open room from them, then that room's
 * onJoin runs with the identity the check returned.
 */
import { LocalDriver } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { authenticateJoin } from "../auth/roomAuth"
import { fakeClient, joinRoom } from "../testing/join"
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
const ORG_A = "3b8d4e6f-0a1c-4d3e-9f4a-5b6c7d8e9f0a"
const ORG_B = "4c9e5f7a-1b2d-4e4f-8a5b-6c7d8e9f0a1b"
const ORG_A_ROOM = { orgId: ORG_A, ownerId: "alice" }
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
    verifiedAs("ana", ORG_A, "Ana")
    const room = createRoom(name, ORG_A_ROOM)
    const raw = { orgId: ORG_A, userId: "alice", name: "Alice", token: "ana-jwt" }

    await joinRoom(room, fakeClient(), raw)

    expect(room.state.players.get("s1")).toMatchObject({ userId: "ana", name: "Ana" })
  })

  it("refuses a client that leaves out orgId before matchmaking could route it", async () => {
    const driver = new LocalDriver()
    createListing(driver, name, "room-a", ORG_A_ROOM)
    verifiedAs("mallory", ORG_B, "Mallory")
    const raw = { ownerId: "alice", token: "mallory-jwt" }

    // The filter alone would send it to org A's room; the static check never lets it get there.
    expect(await findOpenRoom(driver, name, raw)).toBe("room-a")
    await expect(authenticateJoin(undefined, raw)).rejects.toThrow("join must name its org")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("keeps a client that forges another org's orgId out of that org's room", async () => {
    const driver = new LocalDriver()
    createListing(driver, name, "room-a", ORG_A_ROOM)
    verifiedAs("mallory", ORG_B, "Mallory")
    const raw = { orgId: ORG_A, ownerId: "alice", userId: "alice", token: "mallory-jwt" }

    expect(await findOpenRoom(driver, name, raw)).toBe("room-a")
    await expect(authenticateJoin(undefined, raw)).rejects.toThrow("token org mismatch")
  })

  it("keeps a member who names their own org out of another org's room", async () => {
    const room = createRoom(name, ORG_A_ROOM)
    verifiedAs("mallory", ORG_B, "Mallory")
    const raw = { orgId: ORG_B, ownerId: "alice", token: "mallory-jwt" }

    await expect(joinRoom(room, fakeClient(), raw)).rejects.toThrow(
      "join org is not this room's org",
    )
    expect(room.state.players.size).toBe(0)
  })

  it("refuses a tokenless join unless the operator opted in", async () => {
    await expect(
      authenticateJoin(undefined, { orgId: ORG_A, userId: "alice", name: "Alice" }),
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
    expect(() => createRoom("house", { orgId: ORG_A })).toThrow("room needs its ownerId")
  })
})
