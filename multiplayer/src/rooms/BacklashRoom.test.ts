// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { afterEach, describe, expect, it } from "vitest"
import {
  BACKLASH_TURN_MS,
  boardIndex,
  encodeBacklashPiece,
} from "../../../shared/minigames/backlash"
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

function player(userId: string, color: "white" | "black"): BacklashPlayerState {
  const value = new BacklashPlayerState()
  value.userId = userId
  value.color = color
  value.connected = true
  return value
}
