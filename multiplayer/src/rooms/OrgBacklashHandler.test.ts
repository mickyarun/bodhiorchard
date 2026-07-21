// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from "vitest"
import type { Room } from "colyseus"
import { OrgRoomState } from "../schema/OrgRoomState"
import { addActiveBacklash, parseBacklashCreateMessage } from "./OrgBacklashHandler"

describe("parseBacklashCreateMessage", () => {
  it("accepts exactly one non-empty opponent id", () => {
    expect(parseBacklashCreateMessage({ invitedUserId: "user-2" })).toEqual({
      invitedUserId: "user-2",
    })
  })

  it.each([null, undefined, "user-2", [], 42])("rejects non-object input %j", (input) => {
    expect(parseBacklashCreateMessage(input)).toBeNull()
  })

  it.each([
    {},
    { invitedUserId: "" },
    { invitedUserId: 123 },
    { invitedUserId: "x".repeat(65) },
  ])("rejects malformed opponent payload %#", (input) => {
    expect(parseBacklashCreateMessage(input)).toBeNull()
  })
})

describe("addActiveBacklash", () => {
  it("publishes a lobby summary with both participant ids", () => {
    const state = new OrgRoomState()
    const room = { state } as Room<{ state: OrgRoomState }>

    addActiveBacklash(room, "room-1", "host-1", "Alice", "invitee-1")

    const summary = state.activeBacklashes.get("room-1")
    expect(summary).toBeDefined()
    expect(summary?.hostName).toBe("Alice")
    expect(summary?.invitedName).toBe("Opponent")
    expect(summary?.viewerCount).toBe(0)
    expect(Array.from(summary?.viewerNames ?? [])).toEqual([])
    expect(Array.from(summary?.participantUserIds ?? [])).toEqual(["host-1", "invitee-1"])
    expect(summary?.phase).toBe("lobby")
  })
})
