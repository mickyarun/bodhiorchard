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
 * Who may open a race, who may take a lane, and whose name the invites carry.
 * A race is opened only by OrgRaceHandler for the verified host (it holds a
 * one-time create ticket); a client's own `create("race", ...)` has none.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { issueRoomCreateTicket } from "../bridge/RoomCreateTickets"
import {
  createRaceRoom,
  fakeBackend,
  join,
  RACE_ORG,
  send,
  verifiedName,
} from "../testing/raceRoom"
import { RaceRoom } from "./RaceRoom"

const fetchMock = vi.fn()
const rooms: RaceRoom[] = []

const CREATE_OPTIONS = {
  orgId: RACE_ORG,
  hostUserId: "host",
  hostName: "Host",
  distanceM: 100,
  invitedUserIds: ["guest"],
}

function track(room: RaceRoom): RaceRoom {
  rooms.push(room)
  return room
}

/** Bodies of the race-invite POSTs sent to the backend. */
function invitesSent(): Array<Record<string, unknown>> {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/race-invite"))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>)
}

beforeEach(() => {
  fetchMock.mockReset()
  fakeBackend(fetchMock)
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  for (const room of rooms) {
    room.onDispose()
    room.clock.clear()
  }
  rooms.length = 0
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("opening a race", () => {
  it("refuses a create without a server-issued ticket", () => {
    expect(() => new RaceRoom().onCreate(CREATE_OPTIONS)).toThrow(
      "race rooms are created by the server",
    )
    expect(() => new RaceRoom().onCreate({ ...CREATE_OPTIONS, createTicket: "guessed" })).toThrow(
      "race rooms are created by the server",
    )
  })

  it("accepts a ticket once", () => {
    const createTicket = issueRoomCreateTicket("race")
    const first = new RaceRoom()

    first.onCreate({ ...CREATE_OPTIONS, createTicket })
    track(first)

    expect(() => new RaceRoom().onCreate({ ...CREATE_OPTIONS, createTicket })).toThrow(
      "race rooms are created by the server",
    )
  })

  it("refuses a ticket issued for another room type", () => {
    const createTicket = issueRoomCreateTicket("backlash")

    expect(() => new RaceRoom().onCreate({ ...CREATE_OPTIONS, createTicket })).toThrow(
      "race rooms are created by the server",
    )
  })
})

describe("host name", () => {
  it("replaces the name the race was created with by the host's verified name", async () => {
    const room = track(createRaceRoom({ hostName: "The CEO" }))

    await join(room, "s-host", "host")

    expect(room.state.hostName).toBe(verifiedName("host"))
  })

  it("never puts a spoofed host name in an invite", async () => {
    const room = track(createRaceRoom({ hostName: "The CEO" }))
    const host = await join(room, "s-host", "host")

    send(room, host, "race_add_invitees", { userIds: ["newcomer"] })
    await vi.waitFor(() => expect(invitesSent()).toHaveLength(1))

    expect(invitesSent()[0]).toMatchObject({
      recipientUserId: "newcomer",
      hostUserId: "host",
      hostName: verifiedName("host"),
    })
  })

  it("keeps the host name when someone else joins", async () => {
    const room = track(createRaceRoom())

    await join(room, "s-guest", "guest")

    expect(room.state.hostName).toBe("Host")
  })
})

describe("taking a lane", () => {
  it("seats the host and an invited user", async () => {
    const room = track(createRaceRoom())

    await join(room, "s-host", "host")
    await join(room, "s-guest", "guest")

    expect([...room.state.racers.keys()].sort()).toEqual(["guest", "host"])
  })

  it("lets an uninvited org member watch but not race", async () => {
    const room = track(createRaceRoom())

    const watcher = await join(room, "s-watcher", "watcher")

    expect(room.state.racers.has("watcher")).toBe(false)
    expect(watcher.userData).toMatchObject({ userId: "watcher" })
  })

  it("stops seating an invitee who declined", async () => {
    const room = track(createRaceRoom())
    room.removeInvitee("guest")

    await join(room, "s-guest", "guest")

    expect(room.state.racers.has("guest")).toBe(false)
  })
})
