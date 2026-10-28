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
 * A client can send any message with no payload (`room.send("move")`) or a
 * `null` one. Before rooms defined `onUncaughtException`, an exception thrown
 * by a handler escaped the ws listener and exited the server process for
 * every org. Messages are dispatched through the room's registered handlers,
 * the same path Colyseus takes for a decoded client message.
 */
import type { Client, Room } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { PlayerState } from "../schema/PlayerState"
import { BacklashRoom } from "./BacklashRoom"
import { CafeteriaRoom } from "./CafeteriaRoom"
import { CoffeeBarRoom } from "./CoffeeBarRoom"
import { HouseRoom } from "./HouseRoom"
import { MinigameRoom } from "./MinigameRoom"
import { OrgRoom } from "./OrgRoom"
import { RaceRoom } from "./RaceRoom"

const BAD_PAYLOADS: unknown[] = [undefined, null]
const ORG_ID = "6d0c6e2a-3f1b-4f7e-9a55-0f2d8c1b7a44"
const fetchMock = vi.fn()
let errorSpy: ReturnType<typeof vi.spyOn>

function send(room: Room, client: Client, type: string, payload: unknown): void {
  const events = (room as unknown as {
    onMessageEvents: { emit(type: string, client: Client, message: unknown): void }
  }).onMessageEvents
  events.emit(type, client, payload)
}

function fakeClient(sessionId: string, userId: string): Client {
  return { sessionId, userData: { userId, name: userId }, send: vi.fn() } as unknown as Client
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("OrgRoom messages without a payload", () => {
  let room: OrgRoom
  let alice: Client

  beforeEach(async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        orgId: ORG_ID,
        members: [{ user_id: "alice", name: "Alice", character_model: null, presence: "active" }],
        repos: [],
      }),
    )
    room = new OrgRoom()
    await room.onCreate({ orgId: ORG_ID })
    await (room as unknown as { snapshotReady: Promise<void> }).snapshotReady
    alice = fakeClient("s-alice", "alice")
    send(room, alice, "takeover_start", { userId: "alice" })
  })

  afterEach(() => {
    room.setSimulationInterval(undefined)
    room.clock.clear()
    room.onDispose()
  })

  it.each(["move", "takeover_start", "takeover_end", "mount_vehicle", "upgrade_house"])(
    "drops a %s message with an absent or null payload",
    (type) => {
      for (const payload of BAD_PAYLOADS) {
        expect(() => send(room, alice, type, payload)).not.toThrow()
      }
      const member = room.state.members.get("alice")
      expect(member?.takeoverSessionId).toBe("s-alice")
      expect(member?.houseLevel).toBe(1)
      expect(member?.vehicleId).toBe("")
      expect(errorSpy).not.toHaveBeenCalled()
    },
  )
})

describe("HouseRoom messages", () => {
  function houseWithVisitor(): { room: HouseRoom; visitor: PlayerState } {
    const room = new HouseRoom()
    room.onCreate({ orgId: ORG_ID, ownerId: "alice" })
    const visitor = new PlayerState()
    visitor.x = 2
    room.state.players.set("s-bob", visitor)
    return { room, visitor }
  }

  it("drops a move with an absent or null payload and still accepts a valid one", () => {
    const { room, visitor } = houseWithVisitor()
    for (const payload of BAD_PAYLOADS) {
      expect(() => send(room, fakeClient("s-bob", "bob"), "move", payload)).not.toThrow()
    }
    send(room, fakeClient("s-bob", "bob"), "move", { x: 5, z: 1, yaw: 0, animState: "walk" })
    expect(visitor.x).toBe(5)
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it("reports a throwing handler instead of letting it escape", () => {
    const { room } = houseWithVisitor()
    vi.spyOn(room as unknown as { handleMove(): void }, "handleMove").mockImplementation(() => {
      throw new Error("handler bug\nforged line")
    })

    expect(() => send(room, fakeClient("s-bob", "bob"), "move", { x: 1 })).not.toThrow()

    expect(errorSpy).toHaveBeenCalledTimes(1)
    const [format, roomName, , method, message] = errorSpy.mock.calls[0] as unknown[]
    expect(format).toContain("uncaught error")
    expect(roomName).toBe("HouseRoom")
    expect(method).toBe("onMessage")
    expect(message).toBe("handler bug\\nforged line")
  })
})

describe("every room", () => {
  it.each([
    ["OrgRoom", OrgRoom],
    ["HouseRoom", HouseRoom],
    ["CoffeeBarRoom", CoffeeBarRoom],
    ["CafeteriaRoom", CafeteriaRoom],
    ["RaceRoom", RaceRoom],
    ["MinigameRoom", MinigameRoom],
    ["BacklashRoom", BacklashRoom],
  ])("%s handles uncaught exceptions itself", (_name, RoomClass) => {
    expect(typeof RoomClass.prototype.onUncaughtException).toBe("function")
  })
})
