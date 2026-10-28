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
 * One valid token must not be able to open mini-game rooms without limit.
 * Each `create("minigame")` opens a room that lives at least until its seat
 * reservation lapses, so a player may hold only a few open at once; a slot
 * comes back when its room is disposed or its unclaimed seat lapses.
 */
import { matchMaker } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { JoinIdentity } from "../auth/verifyJoin"
import { memberToken, stubBackend } from "../testing/backendStub"
import { fakeClient } from "../testing/join"
import {
  liveRooms,
  matchmakeOverHttp,
  startMatchMaker,
  stopMatchMaker,
} from "../testing/matchMakerServer"
import type { MinigameRoom } from "./MinigameRoom"
import {
  MAX_OPEN_MINIGAMES_PER_USER,
  openMinigameSlots,
  PENDING_SLOT_MS,
  takeMinigameSlot,
} from "./minigameSlots"

const ORG = "6e1d9b62-3f4a-4c7b-8d2e-8f9a0b1c2d3e"
const fetchMock = vi.fn()

function play(userId: string) {
  return matchmakeOverHttp("create", "minigame", {
    orgId: ORG,
    game: "fishing",
    token: memberToken(userId, ORG),
  })
}

/** Fill `userId`'s slots with rooms they never connect to. */
async function openAll(userId: string): Promise<string[]> {
  const seats = []
  for (let i = 0; i < MAX_OPEN_MINIGAMES_PER_USER; i += 1) seats.push(await play(userId))
  return seats.map((seat) => seat.roomId)
}

describe("mini-game rooms per player, through the matchmaker", () => {
  beforeEach(async () => {
    fetchMock.mockReset()
    stubBackend(fetchMock)
    vi.stubGlobal("fetch", fetchMock)
    vi.spyOn(console, "log").mockImplementation(() => undefined)
    vi.spyOn(console, "warn").mockImplementation(() => undefined)
    await startMatchMaker()
  })

  afterEach(async () => {
    await stopMatchMaker()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("refuses a player's game beyond the cap before a room is created", async () => {
    await openAll("ana")

    await expect(play("ana")).rejects.toThrow("too many open mini-games")

    expect(await liveRooms()).toHaveLength(MAX_OPEN_MINIGAMES_PER_USER)
    expect((await play("ben")).roomId).toBeTruthy()
  })

  it("gives the slot back when the player's room is disposed", async () => {
    const [firstRoomId] = await openAll("cara")
    const room = matchMaker.getLocalRoomById(firstRoomId!) as MinigameRoom
    const identity: JoinIdentity = { userId: "cara", name: "cara", orgId: ORG }
    room.onJoin(fakeClient(), {}, identity)
    expect(openMinigameSlots("cara")).toBe(MAX_OPEN_MINIGAMES_PER_USER)

    await room.disconnect()

    expect(openMinigameSlots("cara")).toBe(MAX_OPEN_MINIGAMES_PER_USER - 1)
    expect((await play("cara")).roomId).toBeTruthy()
  })
})

describe("a pending slot", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("lapses once the seat it was taken for can no longer be claimed", () => {
    vi.useFakeTimers()
    for (let i = 0; i < MAX_OPEN_MINIGAMES_PER_USER; i += 1) {
      expect(takeMinigameSlot("dev")).toBe(true)
    }
    expect(takeMinigameSlot("dev")).toBe(false)

    vi.advanceTimersByTime(PENDING_SLOT_MS)

    expect(openMinigameSlots("dev")).toBe(0)
    expect(takeMinigameSlot("dev")).toBe(true)
  })
})
