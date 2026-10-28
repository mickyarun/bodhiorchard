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
 * trust boundary for org rooms. It runs as the static onAuth, before
 * matchmaking, for the org the join names. The backend is faked with a
 * stubbed `fetch`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TOKENLESS_JOIN_FLAG } from "../auth/verifyJoin"
import { OrgRoom } from "./OrgRoom"

const ORG = "5c0e6f8a-2b3d-4e5f-8a6b-7c8d9e0f1a2b"
const OTHER_ORG = "6d1f7a9b-3c4e-4f6a-9b7c-8d9e0f1a2b3c"
const fetchMock = vi.fn()

function verifyReturns(body: unknown, status = 200): void {
  fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status }))
}

/** Join options naming the room's org, as the frontend sends them. */
function joinOptions(extra: Record<string, string>): Record<string, string> {
  return { orgId: ORG, ...extra }
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
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana" })),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("rejects the join in development unless tokenless joins are opted in", async () => {
    vi.stubEnv("NODE_ENV", "development")
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana" })),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("gives an opted-in development join a namespaced identity", async () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    const options = joinOptions({ userId: "u1", name: "Ana" })
    await expect(OrgRoom.onAuth(undefined, options)).resolves.toEqual({
      userId: "dev:u1",
      name: "Ana",
      orgId: ORG,
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("treats an empty token string as no token", async () => {
    vi.stubEnv("NODE_ENV", "production")
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "" })),
    ).rejects.toThrow("auth token required")
  })
})

describe("OrgRoom.onAuth with a token", () => {
  it("asks the backend to verify the token for the org the join names", async () => {
    verifyReturns({ valid: true, user_id: "u1", org_id: ORG, name: "Ana" })

    await OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "jwt" }))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/api\/v1\/internal\/colyseus\/verify-token$/)
    expect(JSON.parse(String(init.body))).toEqual({ token: "jwt", org_id: ORG })
    expect((init.headers as Record<string, string>)["X-Bridge-Secret"]).toBeTruthy()
  })

  it("replaces client-claimed identity with the verified one", async () => {
    verifyReturns({ valid: true, user_id: "real-user", org_id: ORG, name: "Real Name" })

    const result = await OrgRoom.onAuth(undefined, joinOptions({
      userId: "someone-else",
      name: "Spoofed",
      characterModel: "kaykit:mage",
      token: "jwt",
    }))

    expect(result).toEqual({ userId: "real-user", name: "Real Name", orgId: ORG })
  })

  it("rejects a token issued for another org", async () => {
    verifyReturns({ valid: true, user_id: "u1", org_id: OTHER_ORG, name: "Ana" })
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "jwt" })),
    ).rejects.toThrow("token org mismatch")
  })

  it("rejects an invalid or expired token", async () => {
    verifyReturns({ valid: false })
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "bad" })),
    ).rejects.toThrow(/invalid auth token/)
  })

  it("reports a backend HTTP failure distinctly from a bad token", async () => {
    verifyReturns({ detail: "forbidden" }, 403)
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "jwt" })),
    ).rejects.toThrow(/auth backend rejected request/)
  })

  it("reports an unreachable backend distinctly from a bad token", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"))
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "jwt" })),
    ).rejects.toThrow(/auth backend unreachable/)
  })

  it("never accepts the join when verification fails, even in development", async () => {
    vi.stubEnv("NODE_ENV", "development")
    verifyReturns({ valid: false })
    await expect(
      OrgRoom.onAuth(undefined, joinOptions({ userId: "u1", name: "Ana", token: "bad" })),
    ).rejects.toThrow()
  })
})
