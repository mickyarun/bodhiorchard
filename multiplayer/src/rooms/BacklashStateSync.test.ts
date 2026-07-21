// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import {
  Decoder,
  Encoder,
  getDecoderStateCallbacks,
} from "@colyseus/schema"
import { describe, expect, it, vi } from "vitest"
import {
  BACKLASH_BOARD_SIZE,
  boardIndex,
  createBacklashBoard,
  encodeBacklashPiece,
} from "../../../shared/minigames/backlash"
import { BacklashRoomState } from "../schema/BacklashRoomState"

describe("Backlash state serialization", () => {
  it("decodes both ends of a move into the same patch", () => {
    const serverState = new BacklashRoomState()
    serverState.board.push(...createBacklashBoard().map(encodeBacklashPiece))
    const encoder = new Encoder(serverState)
    const clientState = new BacklashRoomState()
    const decoder = new Decoder(clientState)
    decoder.decode(encoder.encodeAll())
    encoder.discardChanges()
    const callbacks = getDecoderStateCallbacks(decoder)
    const boardChanged = vi.fn()
    callbacks(clientState).board.onChange(boardChanged)
    const origin = boardIndex(1, 0)
    const destination = boardIndex(2, 0)

    serverState.board[origin] = ""
    serverState.board[destination] = encodeBacklashPiece({
      id: "white-underling-0",
      color: "white",
      kind: "underling",
    })
    decoder.decode(encoder.encode())

    expect(clientState.board).toHaveLength(BACKLASH_BOARD_SIZE ** 2)
    expect(clientState.board[origin]).toBe("")
    expect(clientState.board[destination]).toBe(serverState.board[destination])
    expect(boardChanged).toHaveBeenCalledTimes(2)
  })
})
