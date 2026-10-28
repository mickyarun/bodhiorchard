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
 * Every room type, through the real matchmaker: a join that is not a verified
 * member of the org it names must be refused before matchmaking creates a
 * room or reserves a seat. A room's own onAuth would run too late (only at
 * WebSocket connect, after the seat is held).
 */
import { matchMaker } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { roomDefinitions } from "../roomDefinitions"
import { backendPaths, memberToken, stubBackend } from "../testing/backendStub"
import {
  liveRooms,
  NO_HEADER_AUTH,
  startMatchMaker,
  stopMatchMaker,
} from "../testing/matchMakerServer"

type RoomName = keyof typeof roomDefinitions
type Matchmake = "joinOrCreate" | "create"

const ORG_A = "0d5f1a3b-7c8e-4f0a-9b1c-2d3e4f5a6b7c"
const ORG_B = "1e6a2b4c-8d9f-4a1b-8c2d-3e4f5a6b7c8d"
const ROOM_NAMES = Object.keys(roomDefinitions) as RoomName[]
const METHODS: Matchmake[] = ["joinOrCreate", "create"]
const fetchMock = vi.fn()

/** The create keys the frontend sends for `name` in `orgId`. */
function roomKeys(name: RoomName, orgId: string): Record<string, string> {
  if (name === "house") return { orgId, ownerId: "alice" }
  if (name === "minigame") return { orgId, game: "fishing" }
  return { orgId }
}

function matchmake(method: Matchmake, name: RoomName, options: Record<string, string>) {
  return matchMaker[method](name, options, NO_HEADER_AUTH)
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
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe.each(ROOM_NAMES)("%s room matchmaking", (name) => {
  it.each(METHODS)("refuses a tokenless %s before any room or seat exists", async (method) => {
    await expect(
      matchmake(method, name, { ...roomKeys(name, ORG_A), userId: "mallory" }),
    ).rejects.toThrow("auth token required")

    expect(await liveRooms()).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(METHODS)("refuses a %s from a member of another org", async (method) => {
    const options = { ...roomKeys(name, ORG_A), token: memberToken("mallory", ORG_B) }

    await expect(matchmake(method, name, options)).rejects.toThrow("token org mismatch")

    expect(await liveRooms()).toEqual([])
    expect(backendPaths(fetchMock)).toEqual(["/api/v1/internal/colyseus/verify-token"])
  })

  it.each([
    ["no org", undefined],
    ["a non-UUID org", "org-a"],
    ["an upper-case org", ORG_A.toUpperCase()],
  ])("refuses a join that names %s without asking the backend", async (_label, orgId) => {
    const options: Record<string, string> = {
      ...roomKeys(name, ORG_A),
      token: memberToken("alice", ORG_A),
    }
    if (orgId === undefined) delete options.orgId
    else options.orgId = orgId

    await expect(matchmake("joinOrCreate", name, options)).rejects.toThrow(
      "join must name its org",
    )

    expect(await liveRooms()).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("a verified member of the org", () => {
  it.each(["org", "house", "coffeebar", "cafeteria", "minigame"] as const)(
    "gets a %s seat that carries the identity the check verified",
    async (name) => {
      const options = { ...roomKeys(name, ORG_A), userId: "bob", token: memberToken("ana", ORG_A) }

      const seat = await matchMaker.joinOrCreate(name, options, NO_HEADER_AUTH)

      const room = matchMaker.getLocalRoomById(seat.roomId)
      const reserved = (room as unknown as { _reservedSeats: Record<string, unknown[]> })
        ._reservedSeats[seat.sessionId]
      expect(reserved?.[1]).toEqual({ userId: "ana", name: "ana", orgId: ORG_A })
      expect(backendPaths(fetchMock).filter((p) => p.endsWith("/verify-token"))).toHaveLength(1)
    },
  )

  it.each(["race", "backlash"] as const)(
    "cannot create a %s room, which only the server opens",
    async (name) => {
      const options = { orgId: ORG_A, hostUserId: "ana", token: memberToken("ana", ORG_A) }

      await expect(matchmake("create", name, options)).rejects.toThrow(
        `${name} rooms are created by the server`,
      )
      expect(await liveRooms()).toEqual([])
    },
  )
})
