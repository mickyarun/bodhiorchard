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
 * Join options are client-controlled, so the userId and room org that the
 * shared join check (verifyJoin) prints must not be able to start a new log
 * line, whether it accepts a development join or refuses one.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TOKENLESS_JOIN_FLAG } from "../auth/verifyJoin"
import { OrgRoomState } from "../schema/OrgRoomState"
import { MinigameRoom } from "./MinigameRoom"
import { OrgRoom } from "./OrgRoom"

const FORGED = "bob\n[OrgRoom] auth ok userId=admin"
const FORGED_ORG = "org\nforged"
let warnSpy: ReturnType<typeof vi.spyOn>

function warnings(): string[] {
  return warnSpy.mock.calls.map((call: unknown[]) => String(call[0]))
}

function orgRoom(orgId: string): OrgRoom {
  const room = new OrgRoom()
  room.setState(new OrgRoomState())
  room.state.orgId = orgId
  return room
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

describe("join check warnings", () => {
  it("escape a forged userId and org on an opted-in tokenless OrgRoom join", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    await orgRoom(FORGED_ORG).onAuth({} as Client, { userId: FORGED, orgId: FORGED_ORG })
    expect(warnings().some((w) => w.includes("bob\\n[OrgRoom]"))).toBe(true)
    expect(warnings().some((w) => w.includes("org\\nforged"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged room org when an OrgRoom join is refused", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ valid: false })))
    await expect(
      orgRoom(FORGED_ORG).onAuth({} as Client, { userId: FORGED, name: "Bob", token: "bad" }),
    ).rejects.toThrow()
    expect(warnings().some((w) => w.includes("join refused"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged userId on an opted-in tokenless MinigameRoom join", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    const room = new MinigameRoom()
    room.onCreate({ game: "fishing", orgId: "org-a" })
    await room.onAuth({} as Client, { userId: FORGED, orgId: "org-a" })
    expect(warnings().some((w) => w.includes("bob\\n[OrgRoom]"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
    room.clock.clear()
  })
})
