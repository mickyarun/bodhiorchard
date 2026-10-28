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
 * OrgRoom client messages: a player may only drive their own character, and
 * only while holding the takeover lock; payloads are validated server-side.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import type { MemberState } from "../schema/MemberState"
import { OrgRoom } from "./OrgRoom"

interface Handlers {
  handleMove(client: Client, data: unknown): void
  handleTakeoverStart(client: Client, data: unknown): void
  handleTakeoverEnd(client: Client, data: unknown): void
  handleMountVehicle(client: Client, data: unknown): void
  handleDismountVehicle(client: Client): void
  handleUpgradeHouse(client: Client, data: unknown): void
}

const T0 = new Date("2026-03-02T10:00:00Z")
const MOVE = { x: 3, y: 0, z: -4, yaw: 1.5, animState: "walk" }

let room: OrgRoom
let h: Handlers

function client(sessionId: string, userId: string): Client {
  return { sessionId, userData: { userId, name: userId }, send: vi.fn() } as unknown as Client
}

function member(userId: string): MemberState {
  const m = room.state.members.get(userId)
  if (!m) throw new Error(`member ${userId} missing`)
  return m
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(T0)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  room = new OrgRoom()
  room.setState(new OrgRoomState())
  room.state.orgId = "org-a"
  room.loadSnapshot({
    orgId: "org-a",
    members: [
      { user_id: "alice", name: "Alice", character_model: null, presence: "active" },
      { user_id: "bob", name: "Bob", character_model: null, presence: "active" },
    ],
    repos: [{ repo_name: "api", growth_stage: 1 }],
  })
  h = room as unknown as Handlers
})

afterEach(() => {
  room.clock.clear()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("takeover lock", () => {
  it("lets a player take control of their own character", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    expect(member("alice").takeoverSessionId).toBe("s-alice")
    expect(member("alice").locationContext).toBe("garden")
  })

  it("refuses to hand another member's character to a player", () => {
    h.handleTakeoverStart(client("s-alice", "alice"), { userId: "bob" })
    expect(member("bob").takeoverSessionId).toBe("")
  })

  it("ignores a takeover for a user who is not in the room", () => {
    const ghost = client("s-ghost", "ghost")
    expect(() => h.handleTakeoverStart(ghost, { userId: "ghost" })).not.toThrow()
    expect(room.state.members.has("ghost")).toBe(false)
  })

  it("only the controlling session can end the takeover", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleTakeoverEnd(client("s-other", "bob"), { userId: "alice" })
    expect(member("alice").takeoverSessionId).toBe("s-alice")

    h.handleTakeoverEnd(alice, { userId: "alice" })
    expect(member("alice").takeoverSessionId).toBe("")
  })

  it("parks the avatar inside an interior instead of walking home", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleMountVehicle(alice, { vehicleId: "horse" })
    h.handleTakeoverEnd(alice, { userId: "alice", location: "cafeteria" })

    const m = member("alice")
    expect(m.locationContext).toBe("cafeteria")
    expect(m.vehicleId).toBe("")
    expect(m.animState).toBe("idle")
  })

  it("walks home when the location is not a known interior", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleTakeoverEnd(alice, { userId: "alice", location: "dungeon" })
    expect(member("alice").locationContext).not.toBe("dungeon")
    expect(member("alice").animState).toBe("walk")
  })

  it("releases the lock when the controlling client disconnects", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    room.onLeave(alice)
    expect(member("alice").takeoverSessionId).toBe("")
  })
})

describe("move", () => {
  it("applies a valid move from the controlling session", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleMove(alice, MOVE)
    expect(member("alice")).toMatchObject({ x: 3, z: -4, yaw: 1.5, animState: "walk" })
  })

  it("ignores moves from a session that does not hold the lock", () => {
    const before = { x: member("alice").x, z: member("alice").z }
    h.handleMove(client("s-alice", "alice"), MOVE)
    expect({ x: member("alice").x, z: member("alice").z }).toEqual(before)
  })

  it.each([
    ["NaN coordinate", { ...MOVE, x: Number.NaN }],
    ["infinite coordinate", { ...MOVE, z: Number.POSITIVE_INFINITY }],
    ["string coordinate", { ...MOVE, y: "1" }],
    ["unknown animation", { ...MOVE, animState: "fly" }],
  ])("rejects a move with %s", (_label, payload) => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    const m = member("alice")
    const before = { x: m.x, y: m.y, z: m.z, yaw: m.yaw, animState: m.animState }
    h.handleMove(alice, payload)
    expect({ x: m.x, y: m.y, z: m.z, yaw: m.yaw, animState: m.animState }).toEqual(before)
  })

  it("drops moves that arrive faster than the 25ms floor", () => {
    const alice = client("s-alice", "alice")
    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleMove(alice, MOVE)
    vi.setSystemTime(T0.getTime() + 10)
    h.handleMove(alice, { ...MOVE, x: 99 })
    expect(member("alice").x).toBe(3)

    vi.setSystemTime(T0.getTime() + 40)
    h.handleMove(alice, { ...MOVE, x: 99 })
    expect(member("alice").x).toBe(99)
  })
})

describe("vehicles and house tier", () => {
  it("mounts only allow-listed vehicles while controlling", () => {
    const alice = client("s-alice", "alice")
    h.handleMountVehicle(alice, { vehicleId: "horse" })
    expect(member("alice").vehicleId).toBe("")

    h.handleTakeoverStart(alice, { userId: "alice" })
    h.handleMountVehicle(alice, { vehicleId: "spaceship" })
    expect(member("alice").vehicleId).toBe("")
    h.handleMountVehicle(alice, { vehicleId: "horse" })
    expect(member("alice").vehicleId).toBe("horse")
    h.handleDismountVehicle(alice)
    expect(member("alice").vehicleId).toBe("")
  })

  it.each([[0], [4], ["3"], [Number.NaN]])("rejects house tier %s", (tier) => {
    h.handleUpgradeHouse(client("s-alice", "alice"), { tier })
    expect(member("alice").houseLevel).toBe(1)
  })

  it("updates only the sender's own house tier", () => {
    h.handleUpgradeHouse(client("s-alice", "alice"), { tier: 2 })
    expect(member("alice").houseLevel).toBe(2)
    expect(member("bob").houseLevel).toBe(1)
  })
})
