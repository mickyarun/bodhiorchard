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
 * An org's garden is one room of `maxClients` seats, and matchmaking holds a
 * seat for every reservation it grants. If unauthenticated reservations were
 * granted, anyone could fill the seats and lock the org's members out (their
 * `joinOrCreate` would then try to open a second room, which the org's
 * bridge slot refuses). These run the real matchmaker.
 */
import { ErrorCode, matchMaker } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { backendPaths, memberToken, stubBackend } from "../testing/backendStub"
import {
  liveRooms,
  NO_HEADER_AUTH,
  reservedSeats,
  startMatchMaker,
  stopMatchMaker,
} from "../testing/matchMakerServer"
import { OrgRoom } from "./OrgRoom"
import { ORG_ROOM_FULL, ORG_ROOM_TAKEN } from "./orgRoomSlot"

const ORG_D = "2f7b3c5d-9e0a-4b2c-9d3e-4f5a6b7c8d9e"
const ORG_B = "3a8c4d6e-0f1b-4c3d-8e4f-5a6b7c8d9e0f"
const FLOOD_SIZE = 150
const fetchMock = vi.fn()

function joinGarden(options: Record<string, string>) {
  return matchMaker.joinOrCreate("org", { orgId: ORG_D, ...options }, NO_HEADER_AUTH)
}

function member(userId: string, orgId = ORG_D): Record<string, string> {
  return { token: memberToken(userId, orgId) }
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

describe("the org's garden under a flood of joins", () => {
  it("grants no seat to tokenless joins and still seats the next member", async () => {
    const first = await joinGarden(member("alice"))
    const garden = matchMaker.getLocalRoomById(first.roomId)

    const flood = await Promise.allSettled(
      Array.from({ length: FLOOD_SIZE }, (_, i) => joinGarden({ userId: `bot-${i}` })),
    )

    expect(flood.every((attempt) => attempt.status === "rejected")).toBe(true)
    expect(reservedSeats(garden)).toBe(1)
    const next = await joinGarden(member("bob"))
    expect(next.roomId).toBe(first.roomId)
    expect(await liveRooms()).toHaveLength(1)
  })

  it("grants no seat to members of another org naming this one", async () => {
    const first = await joinGarden(member("alice"))
    const garden = matchMaker.getLocalRoomById(first.roomId)

    await expect(joinGarden(member("mallory", ORG_B))).rejects.toThrow("token org mismatch")

    expect(reservedSeats(garden)).toBe(1)
  })

  it("asks the backend once per join and fetches the snapshot once per room", async () => {
    await joinGarden(member("alice"))
    await joinGarden(member("bob"))

    expect(backendPaths(fetchMock).filter((p) => p.endsWith("/verify-token"))).toHaveLength(2)
    expect(backendPaths(fetchMock).filter((p) => p.includes("/org-snapshot/"))).toHaveLength(1)
  })
})

describe("a second garden for the same org", () => {
  it("is refused cleanly when the open garden is full", async () => {
    const seats = new OrgRoom().maxClients
    for (let i = 0; i < seats; i += 1) await joinGarden(member(`member-${i}`))

    const refused = joinGarden(member("late"))

    await expect(refused).rejects.toThrow(ORG_ROOM_FULL)
    await expect(refused).rejects.toMatchObject({ code: ErrorCode.MATCHMAKE_INVALID_CRITERIA })
    expect(await liveRooms()).toHaveLength(1)
  })

  it("is refused when a member asks to create one directly", async () => {
    await joinGarden(member("alice"))

    await expect(
      matchMaker.create("org", { orgId: ORG_D, ...member("bob") }, NO_HEADER_AUTH),
    ).rejects.toThrow(ORG_ROOM_TAKEN)
    expect(await liveRooms()).toHaveLength(1)
  })
})
