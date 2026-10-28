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
 * A backlash match is opened only by OrgRoom's `backlash_create` handler,
 * for the verified host, which also delivers the invite. A client's own
 * `create("backlash", ...)` carries no server-issued ticket, so it cannot
 * name any host and invitee it likes or park a lobby for five minutes.
 */
import { matchMaker, type Client, type Room } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { issueRoomCreateTicket } from "../bridge/RoomCreateTickets"
import { OrgRoomState } from "../schema/OrgRoomState"
import { backendPaths, memberToken, stubBackend } from "../testing/backendStub"
import {
  liveRooms,
  NO_HEADER_AUTH,
  startMatchMaker,
  stopMatchMaker,
} from "../testing/matchMakerServer"
import { BacklashRoom } from "./BacklashRoom"
import { installBacklashCreateHandler } from "./OrgBacklashHandler"

type Handler = (client: Client, payload: unknown) => void

const ORG = "4b9d5e7f-1a2c-4d4e-9f5a-6b7c8d9e0f1a"
const CREATE_OPTIONS = { orgId: ORG, hostUserId: "host", invitedUserId: "guest" }
const fetchMock = vi.fn()
const opened: BacklashRoom[] = []

function open(options: Record<string, unknown>): BacklashRoom {
  const room = new BacklashRoom()
  room.roomId = `backlash-${opened.length + 1}`
  room.onCreate(options)
  opened.push(room)
  return room
}

/** An OrgRoom stand-in that records the handlers installed on it. */
function orgRoom(): Map<string, Handler> {
  const handlers = new Map<string, Handler>()
  const state = new OrgRoomState()
  state.orgId = ORG
  installBacklashCreateHandler({
    state,
    onMessage: (type: string, handler: Handler) => handlers.set(type, handler),
  } as unknown as Room<{ state: OrgRoomState }>)
  return handlers
}

beforeEach(async () => {
  fetchMock.mockReset()
  stubBackend(fetchMock)
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  await startMatchMaker()
})

afterEach(async () => {
  for (const room of opened.splice(0)) {
    room.onDispose()
    room.clock.clear()
  }
  await stopMatchMaker()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("opening a backlash match", () => {
  it.each([
    ["no ticket", undefined],
    ["a guessed ticket", "guessed"],
  ])("refuses a create with %s", (_label, createTicket) => {
    expect(() => open({ ...CREATE_OPTIONS, createTicket })).toThrow(
      "backlash rooms are created by the server",
    )
  })

  it("refuses a ticket issued for a race", () => {
    const createTicket = issueRoomCreateTicket("race")

    expect(() => open({ ...CREATE_OPTIONS, createTicket })).toThrow(
      "backlash rooms are created by the server",
    )
  })

  it("accepts a ticket once", () => {
    const createTicket = issueRoomCreateTicket("backlash")

    expect(open({ ...CREATE_OPTIONS, createTicket }).state.hostUserId).toBe("host")
    expect(() => open({ ...CREATE_OPTIONS, createTicket })).toThrow(
      "backlash rooms are created by the server",
    )
  })

  it("opens the match from the verified host's backlash_create and seats the invitee", async () => {
    const host = { userData: { userId: "host", name: "Host" }, send: vi.fn() } as unknown as Client

    orgRoom().get("backlash_create")?.(host, { invitedUserId: "guest" })

    await vi.waitFor(() =>
      expect(host.send).toHaveBeenCalledWith("backlash_created", expect.anything()),
    )
    const [match] = await liveRooms()
    expect(match?.state).toMatchObject({ orgId: ORG, hostUserId: "host", invitedUserId: "guest" })
    expect(backendPaths(fetchMock)).toContain("/api/v1/internal/colyseus/backlash-invite")
    const seat = await matchMaker.joinById(
      match!.roomId,
      { orgId: ORG, token: memberToken("guest", ORG) },
      NO_HEADER_AUTH,
    )
    expect(seat.roomId).toBe(match!.roomId)
  })
})
