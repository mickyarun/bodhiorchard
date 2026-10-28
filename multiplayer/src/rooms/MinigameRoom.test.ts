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
 * MinigameRoom: the server computes and posts the score exactly once; the
 * client can only send inputs. Backend calls go through a stubbed `fetch`.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MinigameRoom } from "./MinigameRoom"

const fetchMock = vi.fn()
/** The verified identity onAuth hands to onJoin. */
const ANA = { userId: "u1", orgId: "org-a", name: "Ana" }
let room: MinigameRoom
let broadcast: ReturnType<typeof vi.spyOn>

function fakeClient(): Client & { send: ReturnType<typeof vi.fn> } {
  return { sessionId: "s1", userData: null, send: vi.fn() } as unknown as Client & {
    send: ReturnType<typeof vi.fn>
  }
}

function createRoom(game: unknown): MinigameRoom {
  const r = new MinigameRoom()
  r.roomId = "mg-room-1"
  r.onCreate({ game })
  broadcast = vi.spyOn(r, "broadcast").mockImplementation(() => r as never)
  vi.spyOn(r, "disconnect").mockResolvedValue(undefined)
  return r
}

function sendInput(data: unknown): void {
  ;(room as unknown as { handleInput(c: Client, d: unknown): void }).handleInput(fakeClient(), data)
}

function postedBodies(path: string): Array<Record<string, unknown>> {
  return fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith(path))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>)
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  room?.onDispose()
  room?.clock.clear()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("MinigameRoom.onAuth", () => {
  it("rejects a tokenless join in production", async () => {
    vi.stubEnv("NODE_ENV", "production")
    room = createRoom("fishing")
    await expect(room.onAuth(fakeClient(), { userId: "u1", orgId: "org-a" })).rejects.toThrow(
      "auth token required",
    )
  })

  it("rejects a token whose org differs from the claimed org", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ valid: true, user_id: "u1", org_id: "org-b" })),
    )
    room = createRoom("fishing")
    await expect(
      room.onAuth(fakeClient(), { userId: "u1", orgId: "org-a", token: "jwt" }),
    ).rejects.toThrow("token org mismatch")
  })

  it("takes user and org from the verified token", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ valid: true, user_id: "u1", org_id: "org-a", name: "Ana" })),
    )
    room = createRoom("fishing")
    const auth = await room.onAuth(fakeClient(), {
      userId: "spoof",
      name: "Spoof",
      orgId: "org-a",
      token: "jwt",
      game: "fishing",
    })
    expect(auth).toEqual({ userId: "u1", orgId: "org-a", name: "Ana" })
  })

  it("rejects an invalid token", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ valid: false })))
    room = createRoom("fishing")
    await expect(
      room.onAuth(fakeClient(), { orgId: "org-a", token: "bad" }),
    ).rejects.toThrow(/invalid auth/)
  })
})

describe("MinigameRoom game lifecycle", () => {
  it("refuses an unknown game and closes the room", () => {
    room = createRoom("chess")
    const client = fakeClient()
    room.onJoin(client, { userId: "u1", orgId: "org-a" })
    expect(room.state.game).toBe("")
    expect(client.send).toHaveBeenCalledWith("mg_error", { reason: "unknown_game" })
    expect(room.disconnect).toHaveBeenCalled()
  })

  it("ignores malformed inputs without throwing", () => {
    room = createRoom("fishing")
    room.onJoin(fakeClient(), {}, ANA)
    const input = (data: unknown): void =>
      (room as unknown as { handleInput(c: Client, d: unknown): void }).handleInput(
        fakeClient(),
        data,
      )
    expect(() => {
      input(null)
      input("cast")
      input({ type: 42 })
      input({ type: "cast", payload: { power: "max" } })
    }).not.toThrow()
    expect(room.state.phase).toBe("playing")
  })

  it("posts the server-computed score exactly once", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ recorded: true, game: "fishing", score: 0, best_score: 0 })),
    )
    room = createRoom("fishing")
    room.onJoin(fakeClient(), {}, ANA)

    room.finish()
    room.finish()
    await vi.waitFor(() => expect(broadcast).toHaveBeenCalledWith("mg_result", expect.anything()))

    const bodies = postedBodies("/minigame-results")
    expect(bodies).toEqual([
      {
        sessionId: "mg-room-1",
        orgId: "org-a",
        userId: "u1",
        userName: "Ana",
        game: "fishing",
        score: room.state.score,
      },
    ])
    expect(room.state.phase).toBe("finished")
  })

  it("refuses a join that skipped verification and posts nothing", async () => {
    room = createRoom("fishing")
    expect(() => room.onJoin(fakeClient(), { userId: "u1", orgId: "org-a" })).toThrow(
      "join was not verified",
    )
    room.finish()
    await vi.waitFor(() => expect(broadcast).toHaveBeenCalledWith("mg_result", expect.anything()))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(broadcast).toHaveBeenCalledWith("mg_result", {
      recorded: false,
      game: "fishing",
      score: 0,
    })
  })

  it("tells the player the score was not recorded when the backend fails", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 500 }))
    room = createRoom("fishing")
    room.onJoin(fakeClient(), {}, ANA)
    room.finish()
    await vi.waitFor(() => expect(broadcast).toHaveBeenCalledWith("mg_result", expect.anything()))
    expect(broadcast).toHaveBeenCalledWith(
      "mg_result",
      expect.objectContaining({ recorded: false, game: "fishing" }),
    )
  })

  it("scores a hook while the game is playing", () => {
    room = createRoom("fishing")
    room.onJoin(fakeClient(), {}, ANA)
    sendInput({ type: "hook", payload: {} })
    expect(broadcast).toHaveBeenCalledWith("fishing_result", expect.anything())
  })

  it("ignores a hook once the game is finished", () => {
    room = createRoom("fishing")
    room.onJoin(fakeClient(), {}, ANA)
    room.finish()
    const scoreAtFinish = room.state.score
    broadcast.mockClear()

    sendInput({ type: "hook", payload: {} })

    expect(broadcast).not.toHaveBeenCalledWith("fishing_result", expect.anything())
    expect(room.state.score).toBe(scoreAtFinish)
  })
})
