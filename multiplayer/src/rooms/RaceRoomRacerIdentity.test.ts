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
 * Each RaceRoom client controls exactly one racer: the user it joined as,
 * verified in onAuth. Clients go through onAuth and onJoin like a real
 * join, and messages are dispatched through the room's registered handlers,
 * the path Colyseus uses for a decoded client message.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { COUNTDOWN_MS } from "../../../shared/race/RaceConstants"
import { RaceRoom } from "./RaceRoom"

interface PhysicsView {
  physicsRacers: Array<{ id: string; isMoving: boolean; sprintUntilMs: number }>
  finishRound(timeoutFired: boolean): Promise<void>
}

const fetchMock = vi.fn()
let room: RaceRoom

function send(client: Client, type: string, payload?: unknown): void {
  const events = (room as unknown as {
    onMessageEvents: { emit(type: string, client: Client, message: unknown): void }
  }).onMessageEvents
  events.emit(type, client, payload)
}

/** Join the room the way Colyseus does: onAuth, then onJoin with its result. */
async function connect(sessionId: string, options: Record<string, string>): Promise<Client> {
  const client = { sessionId, userData: undefined, send: vi.fn() } as unknown as Client
  const auth = await room.onAuth(client, options)
  room.onJoin(client, options, auth)
  room.clients.push(client)
  return client
}

/** A development join without a token, then a racer-slot request. */
async function join(sessionId: string, userId: string): Promise<Client> {
  const client = await connect(sessionId, { userId, name: userId })
  send(client, "race_join", { userId, name: userId })
  return client
}

function physics(): PhysicsView {
  return room as unknown as PhysicsView
}

function startRunning(host: Client): void {
  send(host, "race_start", {})
  const countdown = room.clock.delayed.find((d) => d.time === COUNTDOWN_MS)
  expect(countdown, "countdown timer").toBeDefined()
  countdown?.tick(COUNTDOWN_MS)
  expect(room.state.phase).toBe("running")
}

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "development")
  fetchMock.mockReset().mockResolvedValue(new Response("{}"))
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  room = new RaceRoom()
  room.roomId = "race-identity"
  room.onCreate({
    orgId: "org-a",
    hostUserId: "host",
    hostName: "Host",
    distanceM: 100,
    invitedUserIds: ["guest"],
  })
  vi.spyOn(room, "broadcast").mockImplementation(() => room as never)
})

afterEach(() => {
  room.onDispose()
  room.clock.clear()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("join authentication", () => {
  it("rejects a tokenless join in production", async () => {
    vi.stubEnv("NODE_ENV", "production")
    await expect(connect("s-x", { userId: "host", name: "Host" })).rejects.toThrow(
      "auth token required",
    )
  })

  it("rejects a token issued for another org", async () => {
    fetchMock.mockResolvedValue(Response.json({ valid: true, user_id: "eve", org_id: "org-b" }))
    await expect(connect("s-x", { userId: "eve", token: "jwt" })).rejects.toThrow(
      "token org mismatch",
    )
  })

  it("ignores a race_join that names another user", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ valid: true, user_id: "mallory", org_id: "org-a", name: "Mallory" }),
    )
    const mallory = await connect("s-mallory", { userId: "host", name: "Host", token: "jwt" })
    send(mallory, "race_join", { userId: "host", name: "Host" })
    await join("s-guest", "guest")

    expect(room.state.racers.has("host")).toBe(false)
    expect(room.state.racers.get("mallory")?.name).toBe("Mallory")

    send(mallory, "race_add_invitees", { userIds: ["someone"] })
    send(mallory, "race_cancel", {})
    send(mallory, "race_start", {})
    expect([...room.state.invitedUserIds]).toEqual(["guest"])
    expect(room.broadcast).not.toHaveBeenCalled()
    expect(room.state.phase).toBe("lobby")
  })
})

describe("race inputs", () => {
  it("drive the sender's own racer", async () => {
    const host = await join("s-host", "host")
    await join("s-guest", "guest")
    startRunning(host)

    send(host, "race_move", { userId: "host", isMoving: true })

    expect(physics().physicsRacers.find((r) => r.id === "host")?.isMoving).toBe(true)
  })

  it("cannot move, sprint or jump another racer", async () => {
    const host = await join("s-host", "host")
    const guest = await join("s-guest", "guest")
    startRunning(host)
    const hostRacer = physics().physicsRacers.find((r) => r.id === "host")
    const before = { ...hostRacer }

    send(guest, "race_move", { userId: "host", isMoving: true })
    send(guest, "race_sprint_tap", { userId: "host" })
    send(guest, "race_jump", { userId: "host" })

    expect(hostRacer).toEqual(before)
  })

  it("are ignored from a client without an identity", async () => {
    const host = await join("s-host", "host")
    await join("s-guest", "guest")
    startRunning(host)
    const anonymous = { sessionId: "s-anon", userData: undefined } as unknown as Client

    send(anonymous, "race_move", { userId: "guest", isMoving: true })

    expect(physics().physicsRacers.find((r) => r.id === "guest")?.isMoving).toBe(false)
  })
})

describe("joining twice", () => {
  it("keeps one racer per user, so results carry one row per user", async () => {
    const host = await join("s-host-tab1", "host")
    await join("s-host-tab2", "host")
    await join("s-guest", "guest")
    expect(room.state.racers.size).toBe(2)
    expect(physics().physicsRacers.map((r) => r.id).sort()).toEqual(["guest", "host"])

    startRunning(host)
    await physics().finishRound(true)

    const ids = [...room.state.placings].map((p) => p.racerId)
    expect(ids.sort()).toEqual(["guest", "host"])
  })

  it("lets a racer who reloads mid-race take back control of their own racer", async () => {
    const host = await join("s-host", "host")
    const guest = await join("s-guest", "guest")
    startRunning(host)
    room.onLeave(guest)

    const reloaded = await join("s-guest-reloaded", "guest")
    send(reloaded, "race_move", { userId: "guest", isMoving: true })

    expect(room.state.racers.get("guest")?.connected).toBe(true)
    expect(physics().physicsRacers.find((r) => r.id === "guest")?.isMoving).toBe(true)
    expect(room.state.racers.size).toBe(2)
  })
})

describe("leaving", () => {
  it("marks only the leaving racer as disconnected", async () => {
    await join("s-host", "host")
    const guest = await join("s-guest", "guest")

    room.onLeave(guest)

    expect(room.state.racers.get("guest")?.connected).toBe(false)
    expect(room.state.racers.get("host")?.connected).toBe(true)
  })

  it("keeps a racer connected while another of their sessions is still in the room", async () => {
    await join("s-host", "host")
    const firstTab = await join("s-guest-1", "guest")
    await join("s-guest-2", "guest")

    room.onLeave(firstTab)

    expect(room.state.racers.get("guest")?.connected).toBe(true)
  })

  it("marks a racer connected again when they rejoin", async () => {
    await join("s-host", "host")
    const guest = await join("s-guest", "guest")
    room.onLeave(guest)
    await join("s-guest-again", "guest")
    expect(room.state.racers.get("guest")?.connected).toBe(true)
  })
})
