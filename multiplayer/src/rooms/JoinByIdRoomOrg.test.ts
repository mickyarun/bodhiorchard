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
 * `joinById` names a room, not an org. A verified member of org B who names
 * org B and knows the id of an org D room must not get a seat in it: each
 * seat would be held until its reservation lapsed, so a burst of them would
 * lock org D out of its own room. These go through the matchmaking entry
 * point the HTTP route calls, with the real matchmaker behind it.
 */
import { matchMaker, type Client, type Room } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import { backendPaths, memberToken, stubBackend } from "../testing/backendStub"
import {
  matchmakeOverHttp,
  reservedSeats,
  startMatchMaker,
  stopMatchMaker,
} from "../testing/matchMakerServer"
import { installBacklashCreateHandler } from "./OrgBacklashHandler"
import { installRaceCreateHandler } from "./OrgRaceHandler"

type Handler = (client: Client, payload: unknown) => void
type Opener = () => Promise<string>

const ORG_D = "2f7b3c5d-9e0a-4b2c-9d3e-4f5a6b7c8d9e"
const ORG_B = "3a8c4d6e-0f1b-4c3d-8e4f-5a6b7c8d9e0f"
const ORG_REFUSAL = "join org is not this room's org"
const fetchMock = vi.fn()

function asMember(userId: string, orgId = ORG_D): Record<string, string> {
  return { orgId, token: memberToken(userId, orgId) }
}

async function openShared(name: string, keys: Record<string, string> = {}): Promise<string> {
  const seat = await matchmakeOverHttp("joinOrCreate", name, { ...asMember("alice"), ...keys })
  return seat.roomId
}

/** Open a per-match room the way OrgRoom does, through its handler, for host "alice". */
async function openFromOrgRoom(
  install: (room: Room<{ state: OrgRoomState }>) => void,
  message: string,
  payload: unknown,
): Promise<string> {
  const handlers = new Map<string, Handler>()
  const state = new OrgRoomState()
  state.orgId = ORG_D
  install({
    state,
    onMessage: (type: string, handler: Handler) => handlers.set(type, handler),
  } as unknown as Room<{ state: OrgRoomState }>)
  const host = { userData: { userId: "alice", name: "Alice" }, send: vi.fn() } as unknown as Client
  handlers.get(message)?.(host, payload)
  const reply = `${message.replace("_create", "")}_created`
  await vi.waitFor(() => expect(host.send).toHaveBeenCalledWith(reply, expect.anything()))
  const sent = vi.mocked(host.send).mock.calls.find(([type]) => type === reply)
  return (sent?.[1] as { roomId: string }).roomId
}

const OPENERS: Array<[string, Opener]> = [
  ["org", () => openShared("org")],
  ["house", () => openShared("house", { ownerId: "alice" })],
  ["coffeebar", () => openShared("coffeebar")],
  ["cafeteria", () => openShared("cafeteria")],
  ["race", () => openFromOrgRoom(installRaceCreateHandler, "race_create", {
    invitedUserIds: ["guest"],
    distanceM: 100,
  })],
  ["backlash", () => openFromOrgRoom(installBacklashCreateHandler, "backlash_create", {
    invitedUserId: "guest",
  })],
]

function verifyCalls(): number {
  return backendPaths(fetchMock).filter((path) => path.endsWith("/verify-token")).length
}

beforeEach(async () => {
  fetchMock.mockReset()
  stubBackend(fetchMock)
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  vi.spyOn(console, "error").mockImplementation(() => undefined)
  await startMatchMaker()
})

afterEach(async () => {
  await stopMatchMaker()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe.each(OPENERS)("joinById into an org D %s room", (_name, open) => {
  it("reserves no seat for members of another org, and still seats org D", async () => {
    const roomId = await open()
    const room = matchMaker.getLocalRoomById(roomId)
    const seatsBefore = reservedSeats(room)
    const verifiesBefore = verifyCalls()

    const flood = await Promise.allSettled(
      Array.from({ length: room.maxClients + 1 }, (_, i) =>
        matchmakeOverHttp("joinById", roomId, asMember(`mallory-${i}`, ORG_B)),
      ),
    )

    expect(flood.every((attempt) => attempt.status === "rejected")).toBe(true)
    expect(String((flood[0] as PromiseRejectedResult).reason)).toContain(ORG_REFUSAL)
    expect(reservedSeats(room)).toBe(seatsBefore)
    expect(verifyCalls()).toBe(verifiesBefore)
    const seat = await matchmakeOverHttp("joinById", roomId, asMember("guest"))
    expect(seat.roomId).toBe(roomId)
  })

  it("still refuses a join naming org D with another org's token", async () => {
    const roomId = await open()
    const room = matchMaker.getLocalRoomById(roomId)
    const seatsBefore = reservedSeats(room)

    await expect(
      matchmakeOverHttp("joinById", roomId, { orgId: ORG_D, token: memberToken("mallory", ORG_B) }),
    ).rejects.toThrow("token org mismatch")
    expect(reservedSeats(room)).toBe(seatsBefore)
  })
})

describe("joinById into a mini-game", () => {
  it("refuses another org before it can take the seat", async () => {
    const created = await matchmakeOverHttp("create", "minigame", {
      ...asMember("alice"),
      game: "fishing",
    })
    const room = matchMaker.getLocalRoomById(created.roomId)

    await expect(
      matchmakeOverHttp("joinById", created.roomId, asMember("mallory", ORG_B)),
    ).rejects.toThrow(ORG_REFUSAL)
    expect(reservedSeats(room)).toBe(1)
  })

  it("refuses everyone for a room listed without an org", async () => {
    const listing = await matchMaker.createRoom("minigame", { game: "fishing" })

    await expect(matchmakeOverHttp("joinById", listing.roomId, asMember("alice"))).rejects.toThrow(
      ORG_REFUSAL,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
