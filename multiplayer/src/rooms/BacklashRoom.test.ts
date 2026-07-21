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

afterEach(() => {
  for (const room of rooms) room.clock.clear()
  rooms.length = 0
})

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

    await expect(room.onAuth({} as Client, { userId: "host" })).resolves.toMatchObject({
      userId: "host",
      viewer: false,
    })
    await expect(room.onAuth({} as Client, { userId: "viewer" })).rejects.toThrow(
      "not live yet",
    )

    room.state.phase = "playing"
    await expect(room.onAuth({} as Client, { userId: "viewer" })).resolves.toMatchObject({
      userId: "viewer",
      viewer: true,
    })
  })

  it("tracks viewers without adding them to the player map", () => {
    const room = createRoom("spectator-join-test")
    const client = { sessionId: "viewer-session", userData: null } as unknown as Client

    room.onJoin(client, { userId: "viewer", name: "Sam", viewer: true })

    expect(room.state.viewerCount).toBe(1)
    expect(room.state.players.has("viewer")).toBe(false)
    expect(room.state.viewers.get("viewer-session")).toMatchObject({
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
    const untrustedOptions = { userId: "host", name: "Spoofed host" }
    const authenticated = await room.onAuth(client, { userId: "viewer", name: "Sam" })

    room.onJoin(client, untrustedOptions, authenticated)

    expect(room.state.players.has("host")).toBe(false)
    expect(room.state.viewerCount).toBe(1)
    expect(room.state.viewers.get("viewer-session")?.name).toBe("Sam")
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
    room.onJoin(client, { userId: "viewer", name: "Sam", viewer: true })

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

    encourage({ reaction: "🔥" })
    expect(broadcast).toHaveBeenCalledWith(
      "backlash_encouragement",
      expect.objectContaining({ userId: "viewer", name: "Sam", reaction: "🔥" }),
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
