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
 * OrgRoom.handleBridgeEvent: backend events are untrusted cross-process
 * JSON, so malformed payloads must be dropped without touching state.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import { OrgRoom } from "./OrgRoom"

let room: OrgRoom

function presenceOf(userId: string): string | undefined {
  return room.state.members.get(userId)?.presence
}

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  room = new OrgRoom()
  room.setState(new OrgRoomState())
  room.state.orgId = "org-a"
  room.loadSnapshot({
    orgId: "org-a",
    members: [
      { user_id: "alice", name: "Alice", character_model: null, presence: "active" },
      { user_id: "bob", name: "Bob", character_model: null, presence: "at_home" },
    ],
    repos: [{ repo_name: "api", growth_stage: 1 }],
  })
})

afterEach(() => {
  room.clock.clear()
  vi.restoreAllMocks()
})

describe("member_presence bridge event", () => {
  it("moves the member to the new presence and starts the walk", () => {
    room.handleBridgeEvent("member_presence", { user_id: "alice", presence: "on_break" })
    expect(presenceOf("alice")).toBe("on_break")
    expect(room.state.members.get("alice")?.animState).toBe("walk")
  })

  it("is idempotent for a repeated presence", () => {
    room.handleBridgeEvent("member_presence", { user_id: "bob", presence: "at_home" })
    expect(room.state.members.get("bob")?.animState).not.toBe("walk")
  })

  it.each([
    ["unknown presence", { user_id: "alice", presence: "sleeping" }],
    ["missing user id", { presence: "on_break" }],
    ["empty user id", { user_id: "", presence: "on_break" }],
    ["non-object payload", "on_break"],
    ["null payload", null],
  ])("drops a payload with %s", (_label, data) => {
    room.handleBridgeEvent("member_presence", data as Record<string, unknown>)
    expect(presenceOf("alice")).toBe("active")
  })

  it("ignores presence for a user outside the snapshot", () => {
    room.handleBridgeEvent("member_presence", { user_id: "mallory", presence: "on_break" })
    expect(room.state.members.has("mallory")).toBe(false)
  })

  it("holds a controlled member in place but records the new presence", () => {
    const alice = room.state.members.get("alice")
    if (!alice) throw new Error("alice missing")
    alice.takeoverSessionId = "s-alice"
    room.handleBridgeEvent("member_presence", { user_id: "alice", presence: "at_home" })
    expect(alice.presence).toBe("at_home")
    expect(alice.animState).not.toBe("walk")
  })
})

describe("other bridge events", () => {
  it("drops malformed dev and agent activity payloads", () => {
    expect(() => room.handleBridgeEvent("dev_activity", { nope: true })).not.toThrow()
    expect(() => room.handleBridgeEvent("agent_activity", { nope: true })).not.toThrow()
    expect(room.state.agents.size).toBe(0)
  })

  it("ignores unknown event types", () => {
    expect(() => room.handleBridgeEvent("something_new", {})).not.toThrow()
    expect(presenceOf("alice")).toBe("active")
  })
})

describe("snapshot loading", () => {
  it("assigns members deterministically regardless of backend order", () => {
    const first = [...room.state.members.values()].map((m) => [m.userId, m.x, m.z])
    room.loadSnapshot({
      orgId: "org-a",
      members: [
        { user_id: "bob", name: "Bob", character_model: null, presence: "at_home" },
        { user_id: "alice", name: "Alice", character_model: null, presence: "active" },
      ],
      repos: [{ repo_name: "api", growth_stage: 1 }],
    })
    const second = [...room.state.members.values()].map((m) => [m.userId, m.x, m.z])
    expect(new Map(second.map((r) => [r[0], r]))).toEqual(new Map(first.map((r) => [r[0], r])))
  })

  it("keeps an active takeover across a snapshot reload", () => {
    const alice = room.state.members.get("alice")
    if (!alice) throw new Error("alice missing")
    alice.takeoverSessionId = "s-alice"
    room.loadSnapshot({
      orgId: "org-a",
      members: [{ user_id: "alice", name: "Alice", character_model: null, presence: "active" }],
      repos: [],
    })
    expect(room.state.members.get("alice")?.takeoverSessionId).toBe("s-alice")
    expect(room.state.members.has("bob")).toBe(false)
  })
})
