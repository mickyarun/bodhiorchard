// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from "vitest"
import {
  BACKLASH_BOARD_SIZE,
  applyBacklashMove,
  boardIndex,
  countPieces,
  createBacklashBoard,
  legalMovesForColor,
  legalMovesForPiece,
  positionKey,
  promoteUnderling,
  type BacklashBoard,
  type BacklashPiece,
} from "../../../../shared/minigames/backlash"

function emptyBoard(): BacklashBoard {
  return Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, () => null)
}

function put(
  board: BacklashBoard,
  row: number,
  column: number,
  piece: BacklashPiece,
): number {
  const index = boardIndex(row, column)
  board[index] = piece
  return index
}

const whiteOverling: BacklashPiece = { id: "wo", color: "white", kind: "overling" }
const whiteUnderling: BacklashPiece = { id: "wu", color: "white", kind: "underling" }
const blackOverling: BacklashPiece = { id: "bo", color: "black", kind: "overling" }
const blackUnderling: BacklashPiece = { id: "bu", color: "black", kind: "underling" }

describe("Backlash rules", () => {
  it("creates the official 8x8 starting layout", () => {
    const board = createBacklashBoard()

    expect(board).toHaveLength(64)
    expect(countPieces(board, "white", "overling")).toBe(8)
    expect(countPieces(board, "white", "underling")).toBe(8)
    expect(countPieces(board, "black", "overling")).toBe(8)
    expect(countPieces(board, "black", "underling")).toBe(8)
    expect(board.slice(0, 8).every((piece) => piece?.kind === "overling")).toBe(true)
    expect(board.slice(8, 16).every((piece) => piece?.kind === "underling")).toBe(true)
    expect(board.slice(48, 56).every((piece) => piece?.kind === "underling")).toBe(true)
    expect(board.slice(56, 64).every((piece) => piece?.kind === "overling")).toBe(true)
  })

  it("lets an Overling step one square in all open directions", () => {
    const board = emptyBoard()
    const from = put(board, 3, 3, whiteOverling)

    const steps = legalMovesForPiece(board, from).filter((move) => !move.isJump)

    expect(steps).toHaveLength(8)
  })

  it("jumps friendly pieces without capturing them", () => {
    const board = emptyBoard()
    const from = put(board, 4, 1, whiteOverling)
    put(board, 3, 2, whiteUnderling)
    const to = boardIndex(2, 3)

    const applied = applyBacklashMove(board, { from, to })

    expect(applied?.move.isJump).toBe(true)
    expect(applied?.capturedPiece).toBeNull()
    expect(applied?.board[boardIndex(3, 2)]?.id).toBe("wu")
  })

  it("removes each opposing token jumped during a multi-jump", () => {
    let board = emptyBoard()
    const firstFrom = put(board, 6, 0, blackOverling)
    put(board, 5, 1, whiteUnderling)
    put(board, 3, 3, whiteOverling)

    const first = applyBacklashMove(board, { from: firstFrom, to: boardIndex(4, 2) })
    expect(first?.capturedPiece?.id).toBe("wu")
    board = first!.board
    const second = applyBacklashMove(
      board,
      { from: boardIndex(4, 2), to: boardIndex(2, 4) },
      { jumpOnly: true, excludedLandings: new Set([firstFrom]) },
    )

    expect(second?.capturedPiece?.id).toBe("wo")
    expect(countPieces(second!.board, "white")).toBe(0)
  })

  it("prevents a jump chain from revisiting a prior landing", () => {
    const board = emptyBoard()
    const from = put(board, 4, 2, whiteOverling)
    put(board, 3, 3, whiteUnderling)
    const blockedLanding = boardIndex(2, 4)

    expect(
      legalMovesForPiece(board, from, {
        jumpOnly: true,
        excludedLandings: new Set([blockedLanding]),
      }),
    ).toEqual([])
  })

  it("allows an Underling to capture only a diagonal opponent", () => {
    const board = emptyBoard()
    const from = put(board, 3, 3, whiteUnderling)
    put(board, 2, 2, blackUnderling)
    put(board, 2, 3, blackOverling)
    put(board, 3, 4, whiteOverling)

    const moves = legalMovesForPiece(board, from)

    expect(moves.some((move) => move.to === boardIndex(2, 2) && move.isCapture)).toBe(true)
    expect(moves.some((move) => move.to === boardIndex(2, 3))).toBe(false)
    expect(moves.some((move) => move.to === boardIndex(3, 4))).toBe(false)
  })

  it("promotes only an Underling on the opposing back rank", () => {
    const board = emptyBoard()
    const destination = put(board, 7, 4, whiteUnderling)

    const promoted = promoteUnderling(board, destination)

    expect(promoted?.[destination]).toMatchObject({ id: "wu", kind: "overling" })
    expect(promoteUnderling(board, boardIndex(6, 4))).toBeNull()
  })

  it("returns no legal moves for invalid boards, indexes, and blocked colors", () => {
    const board: BacklashBoard = Array.from(
      { length: BACKLASH_BOARD_SIZE ** 2 },
      (_, index) => ({ id: `blocked-${index}`, color: "white", kind: "underling" }),
    )

    expect(legalMovesForPiece(board, -1)).toEqual([])
    expect(legalMovesForPiece([], 0)).toEqual([])
    expect(legalMovesForColor(board, "white")).toEqual([])
    expect(applyBacklashMove(board, { from: 0, to: 1 })).toBeNull()
  })

  it("uses board contents and side-to-move in repetition keys", () => {
    const board = createBacklashBoard()

    expect(positionKey(board, "white")).not.toBe(positionKey(board, "black"))
    const changed = board.map((piece) => piece ? { ...piece } : null)
    changed[0] = null
    expect(positionKey(changed, "white")).not.toBe(positionKey(board, "white"))
  })
})
