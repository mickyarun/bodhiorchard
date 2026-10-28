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
 * Join options are client-controlled, so the userId and org that the shared
 * join checks (the static onAuth and verifyJoin) print must not be able to
 * start a new log line, whether they accept a development join or refuse one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { authenticateJoin, requireRoomIdentity } from "../auth/roomAuth"
import { TOKENLESS_JOIN_FLAG, verifyJoin } from "../auth/verifyJoin"

const ORG = "9b4d0e2f-6a7c-4d9e-8f0a-1b2c3d4e5f6a"
const FORGED = "bob\n[OrgRoom] auth ok userId=admin"
const FORGED_ORG = "org\nforged"
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

describe("join check warnings", () => {
  it("escape a forged userId on an opted-in tokenless join", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    await authenticateJoin(undefined, { userId: FORGED, orgId: ORG })
    expect(warnings().some((w) => w.includes("bob\\n[OrgRoom]"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged org the static check refuses", async () => {
    await expect(
      authenticateJoin(undefined, { userId: FORGED, orgId: FORGED_ORG, token: "jwt" }),
    ).rejects.toThrow("join must name its org")
    expect(warnings().some((w) => w.includes("org\\nforged"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged org on an opted-in tokenless join verifyJoin refuses", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    await expect(verifyJoin({ userId: FORGED, orgId: ORG }, FORGED_ORG)).rejects.toThrow()
    expect(warnings().some((w) => w.includes("org\\nforged"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged room org when a join is refused", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ valid: false })))
    await expect(
      verifyJoin({ userId: FORGED, name: "Bob", token: "bad" }, FORGED_ORG),
    ).rejects.toThrow()
    expect(warnings().some((w) => w.includes("join refused"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })

  it("escape a forged room org when the room-level check refuses", () => {
    expect(() =>
      requireRoomIdentity({ userId: "bob", name: "Bob", orgId: ORG }, FORGED_ORG),
    ).toThrow("join org is not this room's org")
    expect(warnings().some((w) => w.includes("org\\nforged"))).toBe(true)
    expect(warnings().every((w) => !w.includes("\n"))).toBe(true)
  })
})
