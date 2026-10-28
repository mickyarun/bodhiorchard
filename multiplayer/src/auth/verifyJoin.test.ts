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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  MAX_JOIN_TOKEN_LENGTH,
  requireJoinIdentity,
  TOKENLESS_JOIN_FLAG,
  verifyJoin,
} from "./verifyJoin"

const fetchMock = vi.fn()

/** Make the backend's verify-token endpoint answer with `body`. */
function backendAnswers(body: Record<string, unknown>): void {
  fetchMock.mockImplementation(async () => Response.json(body))
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

describe("verifyJoin with a token", () => {
  it("takes user, name and org from the backend, never from the options", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-a", name: "Alice" })

    const identity = await verifyJoin(
      { token: "jwt", userId: "bob", name: "Bob", orgId: "org-a" },
      "org-a",
    )

    expect(identity).toEqual({ userId: "alice", name: "Alice", orgId: "org-a" })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body))).toEqual({ token: "jwt", org_id: "org-a" })
  })

  it("refuses a room that has no org", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-a", name: "Alice" })

    await expect(verifyJoin({ token: "jwt" }, "")).rejects.toThrow("room has no org")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("refuses when the backend names no user", async () => {
    backendAnswers({ valid: true, org_id: "org-a", name: "Alice" })

    await expect(verifyJoin({ token: "jwt", userId: "bob" }, "org-a")).rejects.toThrow(
      "named no user or org",
    )
  })

  it("refuses when the backend names no org", async () => {
    backendAnswers({ valid: true, user_id: "alice", name: "Alice" })

    await expect(verifyJoin({ token: "jwt", orgId: "org-a" }, "org-a")).rejects.toThrow(
      "named no user or org",
    )
  })

  it("refuses a token whose org is not the room's org", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-b", name: "Alice" })

    await expect(verifyJoin({ token: "jwt", orgId: "org-a" }, "org-a")).rejects.toThrow(
      "token org mismatch",
    )
  })

  it("refuses a token the backend rejects", async () => {
    backendAnswers({ valid: false })

    await expect(verifyJoin({ token: "jwt" }, "org-a")).rejects.toThrow("invalid auth token")
  })

  it("falls back to the verified user id when the backend has no name", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-a", name: "" })

    const identity = await verifyJoin({ token: "jwt", name: "Bob" }, "org-a")

    expect(identity.name).toBe("alice")
  })

  it("refuses an oversized token without forwarding it to the backend", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-a", name: "Alice" })
    const token = "x".repeat(MAX_JOIN_TOKEN_LENGTH + 1)

    await expect(verifyJoin({ token, orgId: "org-a" }, "org-a")).rejects.toThrow(
      "auth token too long",
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("still forwards a token of the longest allowed length", async () => {
    backendAnswers({ valid: true, user_id: "alice", org_id: "org-a", name: "Alice" })
    const token = "x".repeat(MAX_JOIN_TOKEN_LENGTH)

    await expect(verifyJoin({ token, orgId: "org-a" }, "org-a")).resolves.toMatchObject({
      userId: "alice",
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe("verifyJoin without a token", () => {
  it.each([undefined, "", "   "])("refuses token %j when the opt-in flag is off", async (token) => {
    await expect(
      verifyJoin({ token, userId: "bob", orgId: "org-a" }, "org-a"),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("refuses even with the flag on when NODE_ENV is production", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    vi.stubEnv("NODE_ENV", "production")

    await expect(verifyJoin({ userId: "bob", orgId: "org-a" }, "org-a")).rejects.toThrow(
      "auth token required",
    )
  })

  it("gives an opted-in development join a namespaced identity in the room's org", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    vi.stubEnv("NODE_ENV", "development")

    const identity = await verifyJoin({ userId: "bob", name: "Bob", orgId: "org-a" }, "org-a")

    expect(identity).toEqual({ userId: "dev:bob", name: "Bob", orgId: "org-a" })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("keeps an opted-in development join out of an org it did not name", async () => {
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    vi.stubEnv("NODE_ENV", "development")

    await expect(verifyJoin({ userId: "bob", orgId: "org-b" }, "org-a")).rejects.toThrow(
      "org mismatch",
    )
    await expect(verifyJoin({ userId: "bob" }, "org-a")).rejects.toThrow("org mismatch")
    await expect(verifyJoin({ orgId: "org-a" }, "org-a")).rejects.toThrow("needs a userId")
  })
})

describe("requireJoinIdentity", () => {
  it("refuses an onJoin that has no verified identity", () => {
    expect(() => requireJoinIdentity(undefined)).toThrow("join was not verified")
  })
})
