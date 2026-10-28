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
 * Colyseus calls `onJoin(client, rawOptions, authResult)`: the second argument
 * is whatever the client sent, the third is what `onAuth` returned after
 * verifying the JWT. A room that reads identity from the raw options lets any
 * signed-in member act as a colleague. These tests replay the real sequence
 * (onAuth with a token, then onJoin with the same raw options).
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TOKENLESS_JOIN_FLAG } from "../auth/verifyJoin"
import { OrgRoomState } from "../schema/OrgRoomState"
import { MinigameRoom } from "./MinigameRoom"
import { OrgRoom } from "./OrgRoom"

const fetchMock = vi.fn()

function verifiedAs(userId: string, orgId: string, name: string): void {
  fetchMock.mockImplementation(async (url: string) =>
    String(url).endsWith("/verify-token")
      ? Response.json({ valid: true, user_id: userId, org_id: orgId, name })
      : Response.json({ recorded: true }),
  )
}

function orgRoom(orgId: string): OrgRoom {
  const room = new OrgRoom()
  room.setState(new OrgRoomState())
  room.state.orgId = orgId
  return room
}

function fakeClient(): Client {
  return { sessionId: "s1", userData: undefined, send: vi.fn() } as unknown as Client
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("OrgRoom join identity", () => {
  it("binds the client to the verified user, not the user it claimed", async () => {
    verifiedAs("alice", "org-a", "Alice")
    const room = orgRoom("org-a")
    const client = fakeClient()
    const raw = { userId: "bob", name: "Bob", token: "alice-jwt" }

    const auth = await room.onAuth(client, raw)
    await room.onJoin(client, raw, auth)

    expect(client.userData).toMatchObject({ userId: "alice", name: "Alice" })
    room.clock.clear()
  })
  it("refuses a tokenless join in development unless the operator opted in", async () => {
    vi.stubEnv("NODE_ENV", "development")
    const room = orgRoom("org-a")

    await expect(room.onAuth(fakeClient(), { userId: "bob", name: "Bob" })).rejects.toThrow(
      "auth token required",
    )
    expect(fetchMock).not.toHaveBeenCalled()
    room.clock.clear()
  })

  it("binds an opted-in tokenless join to a namespaced dev identity", async () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    const room = orgRoom("org-a")
    const client = fakeClient()
    const raw = { userId: "bob", name: "Bob", orgId: "org-a" }

    const auth = await room.onAuth(client, raw)
    await room.onJoin(client, raw, auth)

    expect(client.userData).toMatchObject({ userId: "dev:bob", name: "Bob" })
    expect(fetchMock).not.toHaveBeenCalled()
    room.clock.clear()
  })

  it("refuses every join to a room created without an org", async () => {
    verifiedAs("alice", "org-a", "Alice")
    const room = orgRoom("")

    await expect(room.onAuth(fakeClient(), { token: "alice-jwt" })).rejects.toThrow(
      "room has no org",
    )
    room.clock.clear()
  })

  it("refuses a token from another org", async () => {
    verifiedAs("alice", "org-b", "Alice")
    const room = orgRoom("org-a")

    await expect(
      room.onAuth(fakeClient(), { token: "alice-jwt", orgId: "org-a" }),
    ).rejects.toThrow("token org mismatch")
    room.clock.clear()
  })

  it("refuses an onJoin that did not pass onAuth", async () => {
    const room = orgRoom("org-a")

    await expect(room.onJoin(fakeClient(), { userId: "bob" })).rejects.toThrow(
      "join was not verified",
    )
    room.clock.clear()
  })
})

describe("MinigameRoom join identity", () => {
  it("records the score for the verified player, not the claimed one", async () => {
    verifiedAs("alice", "org-a", "Alice")
    const room = new MinigameRoom()
    room.roomId = "mg-identity"
    room.onCreate({ game: "fishing" })
    const broadcast = vi.spyOn(room, "broadcast").mockImplementation(() => room as never)
    const client = fakeClient()
    const raw = { game: "fishing", userId: "bob", name: "Bob", orgId: "org-a", token: "alice-jwt" }

    const auth = await room.onAuth(client, raw)
    room.onJoin(client, raw, auth)
    room.finish()
    await vi.waitFor(() => expect(broadcast).toHaveBeenCalledWith("mg_result", expect.anything()))

    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/minigame-results"))
    expect(JSON.parse(String((post?.[1] as RequestInit).body))).toMatchObject({
      userId: "alice",
      userName: "Alice",
      orgId: "org-a",
    })
    expect(room.state.userId).toBe("alice")
    room.onDispose()
    room.clock.clear()
  })

  it("refuses a play whose claimed org is not the token's org", async () => {
    verifiedAs("alice", "org-a", "Alice")
    const room = new MinigameRoom()
    room.onCreate({ game: "fishing" })

    await expect(
      room.onAuth(fakeClient(), { game: "fishing", orgId: "org-b", token: "alice-jwt" }),
    ).rejects.toThrow("token org mismatch")
    await expect(
      room.onAuth(fakeClient(), { game: "fishing", token: "alice-jwt" }),
    ).rejects.toThrow("room has no org")
    room.onDispose()
    room.clock.clear()
  })
})
