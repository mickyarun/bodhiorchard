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
 * RaceRoom lobby authority: only the host starts, cancels or invites; the
 * roster is capped; declines only rewrite the roster before the race runs.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { COUNTDOWN_MS, LOBBY_MAX_MS, MAX_RACERS } from "../../../shared/race/RaceConstants"
import { issueRaceCreateTicket } from "../bridge/RaceCreateTickets"
import { RaceRoom } from "./RaceRoom"

interface LobbyHandlers {
  handleJoin(client: Client, raw: unknown): void
  handleStart(client: Client): void
  handleCancel(client: Client): void
  handleAddInvitees(client: Client, raw: unknown): void
}

const fetchMock = vi.fn()
let room: RaceRoom
let h: LobbyHandlers

function client(sessionId: string): Client {
  return { sessionId, userData: undefined, send: vi.fn() } as unknown as Client
}

/** A client whose join already bound it to `userId`, then asked for a racer slot. */
function join(sessionId: string, userId: string): Client {
  const c = { sessionId, userData: { userId, name: userId }, send: vi.fn() } as unknown as Client
  h.handleJoin(c, { userId, name: userId })
  return c
}

function fireTimer(delayMs: number): void {
  const timer = room.clock.delayed.find((d) => d.time === delayMs)
  expect(timer, `timer for ${delayMs}ms`).toBeDefined()
  timer?.tick(delayMs)
}

function invitePosts(): string[] {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/race-invite"))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)).recipientUserId as string)
}

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(new Response("{}"))
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  room = new RaceRoom()
  room.roomId = "race-lobby-test"
  room.onCreate({
    createTicket: issueRaceCreateTicket(),
    orgId: "org-a",
    hostUserId: "host",
    hostName: "Host",
    distanceM: 100,
    invitedUserIds: ["guest"],
  })
  vi.spyOn(room, "broadcast").mockImplementation(() => room as never)
  vi.spyOn(room, "disconnect").mockResolvedValue(undefined)
  h = room as unknown as LobbyHandlers
})

afterEach(() => {
  room.onDispose()
  room.clock.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("race_join", () => {
  it("seats a racer in the lobby with a lane and marks them connected", () => {
    join("s-host", "host")
    const racer = room.state.racers.get("host")
    expect(racer).toMatchObject({ userId: "host", name: "host", laneIndex: 0, connected: true })
  })

  it.each([
    ["no payload", undefined],
    ["missing name", { userId: "x" }],
    ["empty user id", { userId: "", name: "x" }],
    ["non-string user id", { userId: 9, name: "x" }],
  ])("ignores a join from a client with no verified identity, sending %s", (_label, raw) => {
    h.handleJoin(client("s-x"), raw)
    expect(room.state.racers.size).toBe(0)
  })

  it("closes the roster at MAX_RACERS", () => {
    for (let i = 0; i < MAX_RACERS + 2; i++) room.state.invitedUserIds.push(`racer-${i}`)
    for (let i = 0; i < MAX_RACERS + 2; i++) join(`s-${i}`, `racer-${i}`)
    expect(room.state.racers.size).toBe(MAX_RACERS)
  })

  it("refuses joins once the race has left the lobby", () => {
    const host = join("s-host", "host")
    join("s-guest", "guest")
    h.handleStart(host)
    room.state.invitedUserIds.push("late")
    join("s-late", "late")
    expect(room.state.racers.has("late")).toBe(false)
  })
})

describe("host-only controls", () => {
  it("starts the countdown only for the host with enough racers", () => {
    const host = join("s-host", "host")
    h.handleStart(host)
    expect(room.state.phase).toBe("lobby")

    const guest = join("s-guest", "guest")
    h.handleStart(guest)
    expect(room.state.phase).toBe("lobby")

    h.handleStart(host)
    expect(room.state.phase).toBe("countdown")
    expect(room.clock.delayed.some((d) => d.time === COUNTDOWN_MS)).toBe(true)
  })

  it("lets only the host cancel, and tells everyone", () => {
    const host = join("s-host", "host")
    const guest = join("s-guest", "guest")
    h.handleCancel(guest)
    expect(room.broadcast).not.toHaveBeenCalled()

    h.handleCancel(host)
    expect(room.broadcast).toHaveBeenCalledWith("race_cancelled", { hostName: "Host" })
    expect(room.autoDispose).toBe(true)
  })

  it("ignores a cancel from a client that never joined", () => {
    h.handleCancel(client("s-anon"))
    expect(room.broadcast).not.toHaveBeenCalled()
  })

  it("adds only new invitees, capped at MAX_RACERS, and notifies each once", async () => {
    const host = join("s-host", "host")
    const many = Array.from({ length: MAX_RACERS + 5 }, (_, i) => `new-${i}`)
    h.handleAddInvitees(host, { userIds: ["guest", "host", "", 7, ...many] })

    // host + guest already hold two of the MAX_RACERS seats.
    const added = many.slice(0, MAX_RACERS - 2)
    expect([...room.state.invitedUserIds]).toEqual(["guest", ...added])
    await vi.waitFor(() => expect(invitePosts()).toHaveLength(added.length))
    expect(invitePosts().sort()).toEqual([...added].sort())
  })

  it("rejects invite changes from a non-host", () => {
    join("s-host", "host")
    const guest = join("s-guest", "guest")
    h.handleAddInvitees(guest, { userIds: ["sneaky"] })
    expect([...room.state.invitedUserIds]).toEqual(["guest"])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("invite declines and lobby expiry", () => {
  it("drops a declined invitee and their seat while in the lobby", () => {
    join("s-guest", "guest")
    room.removeInvitee("guest")
    expect([...room.state.invitedUserIds]).toEqual([])
    expect(room.state.racers.has("guest")).toBe(false)
  })

  it("keeps the roster once the race has started", () => {
    const host = join("s-host", "host")
    join("s-guest", "guest")
    h.handleStart(host)
    room.removeInvitee("guest")
    expect([...room.state.invitedUserIds]).toEqual(["guest"])
    expect(room.state.racers.has("guest")).toBe(true)
  })

  it("expires an abandoned lobby after LOBBY_MAX_MS", () => {
    fireTimer(LOBBY_MAX_MS)
    expect(room.autoDispose).toBe(true)
    expect(room.disconnect).toHaveBeenCalled()
  })

  it("does not expire a lobby that already started", () => {
    const host = join("s-host", "host")
    join("s-guest", "guest")
    h.handleStart(host)
    fireTimer(LOBBY_MAX_MS)
    expect(room.disconnect).not.toHaveBeenCalled()
  })
})
