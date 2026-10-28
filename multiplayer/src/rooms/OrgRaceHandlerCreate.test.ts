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
 * The real race-open path: OrgRoom's `race_create` handler issues a create
 * ticket and hands it to `matchMaker.createRoom`, which runs RaceRoom.onCreate.
 * The matchmaker is replaced by a stand-in that runs onCreate in-process.
 */
import type { Client, Room } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { consumeRaceCreateTicket } from "../bridge/RaceCreateTickets"
import { OrgRoomState } from "../schema/OrgRoomState"
import { installRaceCreateHandler } from "./OrgRaceHandler"
import { RaceRoom } from "./RaceRoom"

type Handler = (client: Client, payload: unknown) => void

const { createRoomMock } = vi.hoisted(() => ({ createRoomMock: vi.fn() }))

vi.mock("colyseus", async (importOriginal) => {
  const actual = await importOriginal<typeof import("colyseus")>()
  return { ...actual, matchMaker: { ...actual.matchMaker, createRoom: createRoomMock } }
})

const created: RaceRoom[] = []
const createOptions: Array<Record<string, unknown>> = []

/** An OrgRoom stand-in that records the handlers installed on it. */
function orgRoom(): { room: Room<{ state: OrgRoomState }>; handlers: Map<string, Handler> } {
  const handlers = new Map<string, Handler>()
  const state = new OrgRoomState()
  state.orgId = "org-a"
  const room = {
    state,
    onMessage: (type: string, handler: Handler) => handlers.set(type, handler),
  } as unknown as Room<{ state: OrgRoomState }>
  return { room, handlers }
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")))
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  createRoomMock.mockImplementation(async (_name: string, options: unknown) => {
    createOptions.push(options as Record<string, unknown>)
    const race = new RaceRoom()
    race.roomId = `race-${created.length + 1}`
    race.onCreate(options)
    created.push(race)
    return { roomId: race.roomId } as never
  })
})

afterEach(() => {
  for (const race of created) {
    race.onDispose()
    race.clock.clear()
  }
  created.length = 0
  createOptions.length = 0
  createRoomMock.mockReset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("race_create from the verified host", () => {
  it("opens the race with a ticket that cannot be used again", async () => {
    const { room, handlers } = orgRoom()
    installRaceCreateHandler(room)
    const host = { userData: { userId: "host", name: "Host" }, send: vi.fn() } as unknown as Client

    handlers.get("race_create")?.(host, { invitedUserIds: ["guest"], distanceM: 100 })

    await vi.waitFor(() =>
      expect(host.send).toHaveBeenCalledWith("race_created", { roomId: "race-1" }),
    )
    expect(created[0]?.state.hostUserId).toBe("host")
    expect(consumeRaceCreateTicket(createOptions[0]?.createTicket)).toBe(false)
  })
})
