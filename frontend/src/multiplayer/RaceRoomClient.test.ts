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

import { describe, it, expect } from "vitest"
import { RaceRoomClient } from "./RaceRoomClient"

interface SendCall { type: string; payload: unknown }

/** Minimal Room stand-in — captures the `send` calls the helpers make. */
function fakeRoom(): {
  calls: SendCall[]
  send: (type: string, payload: unknown) => void
  leave: () => Promise<void>
} {
  const calls: SendCall[] = []
  return {
    calls,
    send: (type, payload) => calls.push({ type, payload }),
    leave: () => Promise.resolve(),
  }
}

describe("RaceRoomClient — message shapes", () => {
  it("sendMove produces the expected payload", () => {
    const client = new RaceRoomClient("ws://test")
    const room = fakeRoom()
    // Installing the private fields directly keeps the test free of
    // Colyseus server dependencies while still exercising the real
    // payload-construction code paths.
    ;(client as unknown as { room: typeof room; userId: string }).room = room
    ;(client as unknown as { userId: string }).userId = "user-1"

    client.sendMove(true)

    expect(room.calls).toEqual([
      { type: "race_move", payload: { userId: "user-1", isMoving: true } },
    ])
  })

  it("sendSprintTap carries just the userId", () => {
    const client = new RaceRoomClient("ws://test")
    const room = fakeRoom()
    ;(client as unknown as { room: typeof room; userId: string }).room = room
    ;(client as unknown as { userId: string }).userId = "user-9"

    client.sendSprintTap()

    expect(room.calls).toEqual([{ type: "race_sprint_tap", payload: { userId: "user-9" } }])
  })

  it("sendRaceStart is a UX-only guard — no send when user isn't host", () => {
    const client = new RaceRoomClient("ws://test")
    const room = fakeRoom()
    ;(client as unknown as { room: typeof room }).room = room
    // userId stays "" and snapshot.hostUserId stays "" — not the host.
    client.sendRaceStart()
    expect(room.calls).toEqual([])
  })

  it("sendRaceStart fires when user is the host", () => {
    const client = new RaceRoomClient("ws://test")
    const room = fakeRoom()
    ;(client as unknown as { room: typeof room; userId: string; snapshot: { hostUserId: string } }).room = room
    ;(client as unknown as { userId: string }).userId = "host-1"
    ;(client as unknown as { snapshot: { hostUserId: string } }).snapshot = { hostUserId: "host-1" }

    client.sendRaceStart()
    expect(room.calls).toEqual([{ type: "race_start", payload: {} }])
  })
})
