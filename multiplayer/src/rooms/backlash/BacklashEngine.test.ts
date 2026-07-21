// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from "vitest"
import {
  BACKLASH_BOARD_SIZE,
  boardIndex,
  type BacklashBoard,
} from "../../../../shared/minigames/backlash"
import { BacklashEngine } from "./BacklashEngine"

function sparseBoard(entries: Array<[number, BacklashBoard[number]]>): BacklashBoard {
  const board: BacklashBoard = Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, () => null)
  for (const [index, piece] of entries) board[index] = piece
  return board
}

describe("BacklashEngine", () => {
  it("enforces White first and rejects malformed, stale-side, and occupied moves", () => {
    const engine = new BacklashEngine()

    expect(engine.move("black", boardIndex(6, 0), boardIndex(5, 0))).toMatchObject({
      accepted: false,
      reason: "wrong_turn",
    })
    expect(engine.move("white", -1, 2)).toMatchObject({ accepted: false, reason: "invalid_move" })
    expect(engine.move("white", 0, 8)).toMatchObject({ accepted: false, reason: "invalid_move" })
  })

  it("locks a multi-jump to the same Overling and permits an optional stop", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(6, 0), { id: "wo", color: "white", kind: "overling" }],
      [boardIndex(5, 1), { id: "bu", color: "black", kind: "underling" }],
      [boardIndex(3, 3), { id: "bo", color: "black", kind: "overling" }],
      [boardIndex(7, 7), { id: "bu2", color: "black", kind: "underling" }],
      [boardIndex(0, 0), { id: "wu", color: "white", kind: "underling" }],
    ])

    expect(engine.move("white", boardIndex(6, 0), boardIndex(4, 2))).toMatchObject({
      accepted: true,
      phase: "jump",
    })
    expect(engine.move("white", boardIndex(0, 0), boardIndex(1, 0))).toMatchObject({
      accepted: false,
      reason: "jump_piece_locked",
    })
    expect(engine.endJump("white")).toBe(true)
    expect(engine.turn).toBe("black")
  })

  it("tracks captured Overlings and offers optional promotion", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(2, 2), { id: "wo", color: "white", kind: "overling" }],
      [boardIndex(3, 3), { id: "bo", color: "black", kind: "overling" }],
      [boardIndex(7, 0), { id: "wu", color: "white", kind: "underling" }],
      [boardIndex(7, 7), { id: "bu", color: "black", kind: "underling" }],
    ])

    expect(engine.move("white", boardIndex(2, 2), boardIndex(4, 4)).accepted).toBe(true)
    expect(engine.capturedOverlings.black).toBe(1)
    engine.turn = "black"
    expect(engine.move("black", boardIndex(7, 7), boardIndex(6, 7)).accepted).toBe(true)
    engine.turn = "white"
    expect(engine.move("white", boardIndex(7, 0), boardIndex(6, 0)).accepted).toBe(true)
    expect(engine.phase).toBe("playing")

    engine.board = sparseBoard([
      [boardIndex(1, 0), { id: "bu2", color: "black", kind: "underling" }],
      [boardIndex(7, 7), { id: "wu2", color: "white", kind: "underling" }],
    ])
    engine.turn = "black"
    expect(engine.move("black", boardIndex(1, 0), boardIndex(0, 0)).accepted).toBe(true)
    expect(engine.phase).toBe("promotion")
    expect(engine.resolvePromotion("black", true)).toBe(true)
    expect(engine.board[boardIndex(0, 0)]?.kind).toBe("overling")
    expect(engine.capturedOverlings.black).toBe(0)
  })

  it("finishes when the final opposing token is captured", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(4, 4), { id: "wu", color: "white", kind: "underling" }],
      [boardIndex(3, 3), { id: "bu", color: "black", kind: "underling" }],
    ])

    expect(engine.move("white", boardIndex(4, 4), boardIndex(3, 3)).accepted).toBe(true)
    expect(engine.result).toEqual({ outcome: "win", winnerColor: "white", reason: "all_pieces" })
    expect(engine.move("black", 0, 1).reason).toBe("finished")
  })

  it("records timeout and disconnect forfeits idempotently", () => {
    const engine = new BacklashEngine()
    engine.forfeit("white", "timeout")
    engine.forfeit("black", "disconnect")

    expect(engine.result).toEqual({ outcome: "forfeit", winnerColor: "black", reason: "timeout" })
  })

  it("plays one deterministic legal move instead of forfeiting on inactivity", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(3, 3), { id: "wu", color: "white", kind: "underling" }],
      [boardIndex(7, 7), { id: "bo", color: "black", kind: "overling" }],
    ])

    const result = engine.playAutomaticMove()

    expect(result).toMatchObject({
      accepted: true,
      from: boardIndex(3, 3),
      to: boardIndex(2, 2),
    })
    expect(engine.board[boardIndex(3, 3)]).toBeNull()
    expect(engine.board[boardIndex(2, 2)]?.id).toBe("wu")
    expect(engine.turn).toBe("black")
    expect(engine.result).toBeNull()
  })

  it("finishes safely if an automatic turn has no legal move", () => {
    const engine = new BacklashEngine()
    engine.board = Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, (_, index) => ({
      id: `black-${index}`,
      color: "black" as const,
      kind: "overling" as const,
    }))
    engine.board[boardIndex(0, 0)] = { id: "wo", color: "white", kind: "overling" }

    expect(engine.playAutomaticMove()).toMatchObject({
      accepted: false,
      reason: "no_legal_moves",
      phase: "finished",
    })
    expect(engine.result).toEqual({
      outcome: "win",
      winnerColor: "black",
      reason: "no_legal_moves",
    })
  })

  it("wins when the next player has no legal move", () => {
    const engine = new BacklashEngine()
    engine.board = Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, (_, index) => ({
      id: `bo-${index}`,
      color: "black" as const,
      kind: "overling" as const,
    }))
    for (let row = 1; row <= 5; row += 1) {
      for (let column = 1; column <= 5; column += 1) {
        const index = boardIndex(row, column)
        engine.board[index] = { id: `wu-${index}`, color: "white", kind: "underling" }
      }
    }
    engine.board[boardIndex(2, 2)] = { id: "capturable", color: "black", kind: "overling" }

    expect(engine.move("white", boardIndex(3, 3), boardIndex(2, 2)).accepted).toBe(true)
    expect(engine.result).toEqual({
      outcome: "win",
      winnerColor: "white",
      reason: "no_legal_moves",
    })
  })

  it("draws after three repetitions of the same position", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(0, 0), { id: "wo", color: "white", kind: "overling" }],
      [boardIndex(7, 7), { id: "bo", color: "black", kind: "overling" }],
    ])

    for (let cycle = 0; cycle < 3 && !engine.result; cycle += 1) {
      engine.move("white", boardIndex(0, 0), boardIndex(0, 1))
      engine.move("black", boardIndex(7, 7), boardIndex(7, 6))
      engine.move("white", boardIndex(0, 1), boardIndex(0, 0))
      engine.move("black", boardIndex(7, 6), boardIndex(7, 7))
    }

    expect(engine.result).toEqual({ outcome: "draw", winnerColor: null, reason: "repetition" })
  })

  it("draws at the no-progress turn limit", () => {
    const engine = new BacklashEngine()
    engine.board = sparseBoard([
      [boardIndex(0, 0), { id: "wo", color: "white", kind: "overling" }],
      [boardIndex(7, 7), { id: "bo", color: "black", kind: "overling" }],
    ])
    engine.noProgressTurns = 99

    expect(engine.move("white", boardIndex(0, 0), boardIndex(0, 1)).accepted).toBe(true)
    expect(engine.result).toEqual({ outcome: "draw", winnerColor: null, reason: "no_progress" })
  })

  it("resets all mutable match state for a rematch", () => {
    const engine = new BacklashEngine()
    engine.forfeit("white", "disconnect")
    engine.capturedOverlings.white = 2

    engine.reset()

    expect(engine.phase).toBe("playing")
    expect(engine.turn).toBe("white")
    expect(engine.result).toBeNull()
    expect(engine.capturedOverlings).toEqual({ white: 0, black: 0 })
    expect(engine.board.filter(Boolean)).toHaveLength(32)
  })
})
