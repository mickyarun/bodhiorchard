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
 * is whatever the client sent, the third is what the static `onAuth` returned
 * after verifying the JWT. A room that reads identity from the raw options
 * lets any signed-in member act as a colleague. These tests replay the real
 * sequence (the static onAuth with a token, then onJoin with the same raw
 * options).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { authenticateJoin } from "../auth/roomAuth"
import { TOKENLESS_JOIN_FLAG } from "../auth/verifyJoin"
import { OrgRoomState } from "../schema/OrgRoomState"
import { fakeClient, joinRoom } from "../testing/join"
import { MinigameRoom } from "./MinigameRoom"
import { OrgRoom } from "./OrgRoom"

const ORG_A = "1f6b2c4d-8e9a-4b1c-9d2e-3f4a5b6c7d8e"
const ORG_B = "2a7c3d5e-9f0b-4c2d-8e3f-4a5b6c7d8e9f"
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
    verifiedAs("alice", ORG_A, "Alice")
    const room = orgRoom(ORG_A)
    const client = fakeClient()

    await joinRoom(room, client, { orgId: ORG_A, userId: "bob", name: "Bob", token: "alice-jwt" })

    expect(client.userData).toMatchObject({ userId: "alice", name: "Alice" })
    room.clock.clear()
  })

  it("refuses a tokenless join in development unless the operator opted in", async () => {
    vi.stubEnv("NODE_ENV", "development")

    await expect(
      authenticateJoin(undefined, { orgId: ORG_A, userId: "bob", name: "Bob" }),
    ).rejects.toThrow("auth token required")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("binds an opted-in tokenless join to a namespaced dev identity", async () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv(TOKENLESS_JOIN_FLAG, "1")
    const room = orgRoom(ORG_A)
    const client = fakeClient()

    await joinRoom(room, client, { userId: "bob", name: "Bob", orgId: ORG_A })

    expect(client.userData).toMatchObject({ userId: "dev:bob", name: "Bob" })
    expect(fetchMock).not.toHaveBeenCalled()
    room.clock.clear()
  })

  it("refuses every join to a room created without an org", async () => {
    verifiedAs("alice", ORG_A, "Alice")
    const room = orgRoom("")

    await expect(
      joinRoom(room, fakeClient(), { orgId: ORG_A, token: "alice-jwt" }),
    ).rejects.toThrow("join org is not this room's org")
    room.clock.clear()
  })

  it("refuses a token from another org", async () => {
    verifiedAs("alice", ORG_B, "Alice")

    await expect(
      authenticateJoin(undefined, { token: "alice-jwt", orgId: ORG_A }),
    ).rejects.toThrow("token org mismatch")
  })

  it("refuses a member verified in their own org who lands in another org's room", async () => {
    verifiedAs("mallory", ORG_B, "Mallory")
    const room = orgRoom(ORG_A)
    const client = fakeClient()

    await expect(
      joinRoom(room, client, { orgId: ORG_B, token: "mallory-jwt" }),
    ).rejects.toThrow("join org is not this room's org")
    expect(client.userData).toBeUndefined()
    room.clock.clear()
  })

  it("refuses an onJoin that did not pass onAuth", async () => {
    const room = orgRoom(ORG_A)

    await expect(room.onJoin(fakeClient(), { userId: "bob" })).rejects.toThrow(
      "join was not verified",
    )
    room.clock.clear()
  })
})

describe("MinigameRoom join identity", () => {
  it("records the score for the verified player, not the claimed one", async () => {
    verifiedAs("alice", ORG_A, "Alice")
    const room = new MinigameRoom()
    room.roomId = "mg-identity"
    room.onCreate({ game: "fishing" })
    const broadcast = vi.spyOn(room, "broadcast").mockImplementation(() => room as never)
    const raw = { game: "fishing", userId: "bob", name: "Bob", orgId: ORG_A, token: "alice-jwt" }

    await joinRoom(room, fakeClient(), raw)
    room.finish()
    await vi.waitFor(() => expect(broadcast).toHaveBeenCalledWith("mg_result", expect.anything()))

    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/minigame-results"))
    expect(JSON.parse(String((post?.[1] as RequestInit).body))).toMatchObject({
      userId: "alice",
      userName: "Alice",
      orgId: ORG_A,
    })
    expect(room.state.userId).toBe("alice")
    room.onDispose()
    room.clock.clear()
  })

  it("refuses a play whose claimed org is not the token's org", async () => {
    verifiedAs("alice", ORG_A, "Alice")

    await expect(
      authenticateJoin(undefined, { orgId: ORG_B, token: "alice-jwt" }),
    ).rejects.toThrow("token org mismatch")
    await expect(
      authenticateJoin(undefined, { token: "alice-jwt" }),
    ).rejects.toThrow("join must name its org")
  })
})
