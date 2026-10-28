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
 * Join options are client-controlled, so the userId and orgId that onAuth
 * prints must not be able to start a new log line.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import { MinigameRoom } from "./MinigameRoom"
import { OrgRoom } from "./OrgRoom"

const FORGED = "bob\n[OrgRoom] auth ok userId=admin"
let warnSpy: ReturnType<typeof vi.spyOn>

function warnings(): string[] {
  return warnSpy.mock.calls.map((call: unknown[]) => String(call[0]))
}

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "development")
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("onAuth warnings", () => {
  it("escape a forged userId and orgId on a tokenless OrgRoom join", async () => {
    const room = new OrgRoom()
    room.setState(new OrgRoomState())
    room.state.orgId = "org\nforged"
    await room.onAuth({} as Client, { userId: FORGED, name: "Bob" })
    expect(warnings().some((w) => w.includes("bob\\n[OrgRoom]"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged userId when OrgRoom auth fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ valid: false })))
    const room = new OrgRoom()
    room.setState(new OrgRoomState())
    room.state.orgId = "org-a"
    await expect(
      room.onAuth({} as Client, { userId: FORGED, name: "Bob", token: "bad" }),
    ).rejects.toThrow()
    expect(warnings().some((w) => w.includes("auth failed"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged userId on a tokenless MinigameRoom join", async () => {
    const room = new MinigameRoom()
    room.onCreate({ game: "fishing" })
    await room.onAuth({} as Client, { userId: FORGED })
    expect(warnings().some((w) => w.includes("bob\\n[OrgRoom]"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
    room.clock.clear()
  })
})
