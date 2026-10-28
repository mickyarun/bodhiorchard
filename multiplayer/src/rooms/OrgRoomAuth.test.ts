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
 * OrgRoom join authentication: the JWT check against the backend is the only
 * trust boundary for org rooms. The backend is faked with a stubbed `fetch`.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import { OrgRoom } from "./OrgRoom"

const CLIENT = {} as Client
const fetchMock = vi.fn()

function verifyReturns(body: unknown, status = 200): void {
  fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status }))
}

function roomFor(orgId: string): OrgRoom {
  const room = new OrgRoom()
  room.setState(new OrgRoomState())
  room.state.orgId = orgId
  return room
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("OrgRoom.onAuth without a token", () => {
  it("rejects the join in production", async () => {
    vi.stubEnv("NODE_ENV", "production")
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana" }),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("accepts the client-supplied identity in development", async () => {
    vi.stubEnv("NODE_ENV", "development")
    const options = { userId: "u1", name: "Ana" }
    await expect(roomFor("org-a").onAuth(CLIENT, options)).resolves.toEqual(options)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("treats an empty token string as no token", async () => {
    vi.stubEnv("NODE_ENV", "production")
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "" }),
    ).rejects.toThrow("auth token required")
  })
})

describe("OrgRoom.onAuth with a token", () => {
  it("asks the backend to verify the token for this room's org", async () => {
    verifyReturns({ valid: true, user_id: "u1", org_id: "org-a", name: "Ana" })

    await roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "jwt" })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/v1\/internal\/colyseus\/verify-token$/)
    expect(JSON.parse(String(init.body))).toEqual({ token: "jwt", org_id: "org-a" })
    expect((init.headers as Record<string, string>)["X-Bridge-Secret"]).toBeTruthy()
  })

  it("replaces client-claimed identity with the verified one", async () => {
    verifyReturns({ valid: true, user_id: "real-user", org_id: "org-a", name: "Real Name" })

    const result = await roomFor("org-a").onAuth(CLIENT, {
      userId: "someone-else",
      name: "Spoofed",
      characterModel: "kaykit:mage",
      token: "jwt",
    })

    expect(result).toMatchObject({
      userId: "real-user",
      name: "Real Name",
      characterModel: "kaykit:mage",
    })
  })

  it("rejects a token issued for another org", async () => {
    verifyReturns({ valid: true, user_id: "u1", org_id: "org-b", name: "Ana" })
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "jwt" }),
    ).rejects.toThrow("token org mismatch")
  })

  it("rejects an invalid or expired token", async () => {
    verifyReturns({ valid: false })
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "bad" }),
    ).rejects.toThrow(/invalid auth token/)
  })

  it("reports a backend HTTP failure distinctly from a bad token", async () => {
    verifyReturns({ detail: "forbidden" }, 403)
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "jwt" }),
    ).rejects.toThrow(/auth backend rejected request/)
  })

  it("reports an unreachable backend distinctly from a bad token", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"))
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "jwt" }),
    ).rejects.toThrow(/auth backend unreachable/)
  })

  it("never accepts the join when verification fails, even in development", async () => {
    vi.stubEnv("NODE_ENV", "development")
    verifyReturns({ valid: false })
    await expect(
      roomFor("org-a").onAuth(CLIENT, { userId: "u1", name: "Ana", token: "bad" }),
    ).rejects.toThrow()
  })
})
