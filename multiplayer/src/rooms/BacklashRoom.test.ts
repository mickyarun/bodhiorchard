// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import type { Client } from "colyseus"
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  BACKLASH_TURN_MS,
  boardIndex,
  encodeBacklashPiece,
} from "../../../shared/minigames/backlash"
import {
  fireBacklashDispose,
  registerBacklashSummaryHooks,
} from "../bridge/BacklashRegistry"
import { BacklashPlayerState, BacklashRoomState } from "../schema/BacklashRoomState"
import { BacklashRoom } from "./BacklashRoom"

const rooms: BacklashRoom[] = []
const fetchMock = vi.fn()

afterEach(() => {
  for (const room of rooms) room.clock.clear()
  rooms.length = 0
  fetchMock.mockReset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Make the backend verify every token as `userId` in org-1. */
function verifiedAs(userId: string, orgId = "org-1"): void {
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  fetchMock.mockImplementation(async () =>
    Response.json({ valid: true, user_id: userId, org_id: orgId, name: userId }),
  )
}

/** The verified identity onAuth hands onJoin for a viewer. */
function viewerAuth(userId = "viewer", name = "Sam") {
  return { userId, name, orgId: "org-1", viewer: true }
}

describe("BacklashRoom turn timeout", () => {
  it("applies and synchronizes a legal move instead of forfeiting the inactive player", () => {
    const room = new BacklashRoom()
    rooms.push(room)
    room.roomId = "timeout-autoplay-test"
    const state = new BacklashRoomState()
    state.hostUserId = "white-player"
    state.invitedUserId = "black-player"
    state.players.set("white-player", player("white-player", "white"))
    state.players.set("black-player", player("black-player", "black"))
    room.setState(state)

    ;(room as unknown as { startMatch: () => void }).startMatch()
    const synchronizedState = room.state
    const firstDeadline = synchronizedState.turnDeadlineMs
    expect(room.clock.delayed).toHaveLength(1)
    const turnTimeout = room.clock.delayed[0]
    turnTimeout?.tick(BACKLASH_TURN_MS)
    expect(turnTimeout?.active).toBe(false)

    expect(synchronizedState.phase).toBe("playing")
    expect(synchronizedState.outcome).toBe("")
    expect(synchronizedState.moveCount).toBe(1)
    expect(synchronizedState.revision).toBe(1)
    expect(synchronizedState.turnColor).toBe("black")
    expect(synchronizedState.board[boardIndex(0, 0)]).toBe("")
    expect(synchronizedState.board[boardIndex(2, 0)]).toBe(encodeBacklashPiece({
      id: "white-overling-0",
      color: "white",
      kind: "overling",
    }))
    expect(synchronizedState.turnDeadlineMs).toBeGreaterThanOrEqual(firstDeadline)
  })
})

describe("BacklashRoom spectators", () => {
  it("accepts participants in the lobby but viewers only after play starts", async () => {
    const room = createRoom("spectator-auth-test")
    room.state.orgId = "org-1"
    room.state.hostUserId = "host"
    room.state.invitedUserId = "invitee"

    verifiedAs("host")
    await expect(room.onAuth({} as Client, { token: "jwt" })).resolves.toMatchObject({
      userId: "host",
      viewer: false,
    })
    verifiedAs("viewer")
    await expect(room.onAuth({} as Client, { token: "jwt" })).rejects.toThrow(
      "not live yet",
    )

    room.state.phase = "playing"
    await expect(room.onAuth({} as Client, { token: "jwt" })).resolves.toMatchObject({
      userId: "viewer",
      viewer: true,
    })
  })

  it("refuses a tokenless join and a token from another org", async () => {
    const room = createRoom("spectator-org-test")
    room.state.orgId = "org-1"
    room.state.hostUserId = "host"
    room.state.phase = "playing"
    verifiedAs("host", "org-2")

    await expect(room.onAuth({} as Client, { userId: "host" })).rejects.toThrow(
      "auth token required",
    )
    await expect(room.onAuth({} as Client, { token: "jwt" })).rejects.toThrow(
      "token org mismatch",
    )
  })

  it("refuses an onJoin that did not pass onAuth", () => {
    const room = createRoom("spectator-unverified-test")
    const client = { sessionId: "s", userData: null } as unknown as Client

    expect(() => room.onJoin(client, { userId: "host", name: "Host" })).toThrow(
      "join was not verified",
    )
  })

  it("tracks viewers without adding them to the player map", () => {
    const room = createRoom("spectator-join-test")
    const client = { sessionId: "viewer-session", userData: null } as unknown as Client

    room.onJoin(client, {}, viewerAuth())

    expect(room.state.viewerCount).toBe(1)
    expect(room.state.players.has("viewer")).toBe(false)
    expect(room.state.viewers.get("viewer")).toMatchObject({
      userId: "viewer",
      name: "Sam",
    })
    expect(client.userData).toEqual({ userId: "viewer", name: "Sam", viewer: true })
  })

  it("uses the authenticated identity instead of untrusted join options", async () => {
    const room = createRoom("spectator-auth-handoff-test")
    room.state.orgId = "org-1"
    room.state.hostUserId = "host"
    room.state.invitedUserId = "invitee"
    room.state.phase = "playing"
    const client = { sessionId: "viewer-session", userData: null } as unknown as Client
    const untrustedOptions = { userId: "host", name: "Spoofed host", token: "jwt" }
    verifiedAs("viewer")
    const authenticated = await room.onAuth(client, untrustedOptions)

    room.onJoin(client, untrustedOptions, authenticated)

    expect(room.state.players.has("host")).toBe(false)
    expect(room.state.viewerCount).toBe(1)
    expect(room.state.viewers.get("viewer")?.name).toBe("viewer")
  })

  it("counts one watcher per user across multiple sessions", async () => {
    const room = createRoom("spectator-deduplication-test")
    const firstClient = {
      sessionId: "viewer-session-1",
      userData: null,
    } as unknown as Client
    const secondClient = {
      sessionId: "viewer-session-2",
      userData: null,
    } as unknown as Client

    room.onJoin(firstClient, {}, viewerAuth())
    room.onJoin(secondClient, {}, viewerAuth())

    expect(room.state.viewerCount).toBe(1)
    expect(room.state.viewers.size).toBe(1)

    await room.onLeave(firstClient, 1000)
    expect(room.state.viewerCount).toBe(1)
    expect(room.state.viewers.has("viewer")).toBe(true)

    await room.onLeave(secondClient, 1000)
    expect(room.state.viewerCount).toBe(0)
    expect(room.state.viewers.size).toBe(0)
  })

  it("removes a viewer immediately after a consented leave", async () => {
    const room = createRoom("spectator-leave-test")
    const client = { sessionId: "viewer-session", userData: null } as unknown as Client
    const onViewers = vi.fn()
    registerBacklashSummaryHooks(room.roomId, {
      onDispose: vi.fn(),
      onPhase: vi.fn(),
      onViewers,
    })
    room.onJoin(client, {}, viewerAuth())

    expect(onViewers).toHaveBeenLastCalledWith(["Sam"])

    await room.onLeave(client, 1000)

    expect(room.state.viewerCount).toBe(0)
    expect(room.state.viewers.size).toBe(0)
    expect(onViewers).toHaveBeenLastCalledWith([])
    fireBacklashDispose(room.roomId)
  })

  it("validates and rate-limits encouragements on the server", () => {
    const room = createRoom("encouragement-test")
    room.state.phase = "playing"
    const send = vi.fn()
    const client = {
      userData: { userId: "viewer", name: "Sam" },
      send,
    } as unknown as Client
    const broadcast = vi.spyOn(room, "broadcast").mockImplementation(() => room)
    const encourage = (raw: unknown): void => {
      ;(room as unknown as {
        handleEncouragement: (value: Client, payload: unknown) => void
      }).handleEncouragement(client, raw)
    }

    encourage({ reaction: "not-allowed" })
    expect(send).toHaveBeenCalledWith("backlash_error", { reason: "invalid_encouragement" })

    encourage({ reaction: "😭" })
    expect(broadcast).toHaveBeenCalledWith(
      "backlash_encouragement",
      expect.objectContaining({ userId: "viewer", name: "Sam", reaction: "😭" }),
    )

    encourage({ reaction: "👏" })
    expect(send).toHaveBeenCalledWith("backlash_error", {
      reason: "encouragement_rate_limited",
    })
    expect(broadcast).toHaveBeenCalledTimes(1)
  })
})

function createRoom(roomId: string): BacklashRoom {
  const room = new BacklashRoom()
  rooms.push(room)
  room.roomId = roomId
  room.setState(new BacklashRoomState())
  return room
}

function player(userId: string, color: "white" | "black"): BacklashPlayerState {
  const value = new BacklashPlayerState()
  value.userId = userId
  value.color = color
  value.connected = true
  return value
}
