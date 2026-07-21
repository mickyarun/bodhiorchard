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
 * Pure Backlash rules shared by the authoritative Colyseus room and the UI.
 * The client uses these helpers only for highlighting; the server always
 * validates and applies the move again against its authoritative board.
 */

export const BACKLASH_BOARD_SIZE = 8
export const BACKLASH_STARTING_PIECES_PER_KIND = 8
export const BACKLASH_TURN_MS = 60_000
export const BACKLASH_RECONNECT_SECONDS = 30
export const BACKLASH_LOBBY_MS = 5 * 60_000
export const BACKLASH_REMATCH_MS = 30_000
export const BACKLASH_PROMOTION_MS = 10_000
export const BACKLASH_NO_PROGRESS_TURN_LIMIT = 100
export const BACKLASH_REPETITION_LIMIT = 3

export type BacklashColor = "white" | "black"
export type BacklashPieceKind = "overling" | "underling"
export type BacklashOutcome = "win" | "draw" | "forfeit"

export interface BacklashPiece {
  id: string
  color: BacklashColor
  kind: BacklashPieceKind
}

export type BacklashBoard = Array<BacklashPiece | null>

export interface BacklashMove {
  from: number
  to: number
  jumped: number | null
  isJump: boolean
  isCapture: boolean
}

export interface BacklashAppliedMove {
  board: BacklashBoard
  move: BacklashMove
  movedPiece: BacklashPiece
  capturedPiece: BacklashPiece | null
  promotionAvailable: boolean
}

const DIRECTIONS: ReadonlyArray<readonly [number, number]> = [
  [-1, -1], [-1, 0], [-1, 1],
  [0, -1], [0, 1],
  [1, -1], [1, 0], [1, 1],
]

export function opponentColor(color: BacklashColor): BacklashColor {
  return color === "white" ? "black" : "white"
}

export function boardIndex(row: number, column: number): number {
  return row * BACKLASH_BOARD_SIZE + column
}

export function boardCoordinates(index: number): { row: number; column: number } {
  return {
    row: Math.floor(index / BACKLASH_BOARD_SIZE),
    column: index % BACKLASH_BOARD_SIZE,
  }
}

export function isBoardIndex(index: number): boolean {
  return Number.isInteger(index) && index >= 0 && index < BACKLASH_BOARD_SIZE ** 2
}

function isInside(row: number, column: number): boolean {
  return row >= 0 && row < BACKLASH_BOARD_SIZE && column >= 0 && column < BACKLASH_BOARD_SIZE
}

export function createBacklashBoard(): BacklashBoard {
  const board: BacklashBoard = Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, () => null)
  for (let column = 0; column < BACKLASH_BOARD_SIZE; column += 1) {
    board[boardIndex(0, column)] = piece("white", "overling", column)
    board[boardIndex(1, column)] = piece("white", "underling", column)
    board[boardIndex(6, column)] = piece("black", "underling", column)
    board[boardIndex(7, column)] = piece("black", "overling", column)
  }
  return board
}

function piece(color: BacklashColor, kind: BacklashPieceKind, ordinal: number): BacklashPiece {
  return { id: `${color}-${kind}-${ordinal}`, color, kind }
}

export function legalMovesForPiece(
  board: readonly (BacklashPiece | null)[],
  from: number,
  options: { jumpOnly?: boolean; excludedLandings?: ReadonlySet<number> } = {},
): BacklashMove[] {
  if (!isBoardIndex(from) || board.length !== BACKLASH_BOARD_SIZE ** 2) return []
  const moving = board[from]
  if (!moving) return []

  const { row, column } = boardCoordinates(from)
  const moves: BacklashMove[] = []
  for (const [rowDelta, columnDelta] of DIRECTIONS) {
    if (moving.kind === "overling") {
      const jumpRow = row + rowDelta * 2
      const jumpColumn = column + columnDelta * 2
      const middleRow = row + rowDelta
      const middleColumn = column + columnDelta
      if (isInside(jumpRow, jumpColumn) && isInside(middleRow, middleColumn)) {
        const middle = boardIndex(middleRow, middleColumn)
        const landing = boardIndex(jumpRow, jumpColumn)
        const jumpedPiece = board[middle]
        if (
          jumpedPiece
          && !board[landing]
          && !options.excludedLandings?.has(landing)
        ) {
          moves.push({
            from,
            to: landing,
            jumped: middle,
            isJump: true,
            isCapture: jumpedPiece.color !== moving.color,
          })
        }
      }

      if (!options.jumpOnly) {
        const stepRow = row + rowDelta
        const stepColumn = column + columnDelta
        if (isInside(stepRow, stepColumn)) {
          const destination = boardIndex(stepRow, stepColumn)
          if (!board[destination]) {
            moves.push({ from, to: destination, jumped: null, isJump: false, isCapture: false })
          }
        }
      }
      continue
    }

    if (options.jumpOnly) continue
    const destinationRow = row + rowDelta
    const destinationColumn = column + columnDelta
    if (!isInside(destinationRow, destinationColumn)) continue
    const destination = boardIndex(destinationRow, destinationColumn)
    const occupant = board[destination]
    if (!occupant) {
      moves.push({ from, to: destination, jumped: null, isJump: false, isCapture: false })
      continue
    }
    const diagonal = rowDelta !== 0 && columnDelta !== 0
    if (diagonal && occupant.color !== moving.color) {
      moves.push({ from, to: destination, jumped: null, isJump: false, isCapture: true })
    }
  }
  return moves
}

export function legalMovesForColor(
  board: readonly (BacklashPiece | null)[],
  color: BacklashColor,
): BacklashMove[] {
  const moves: BacklashMove[] = []
  for (let index = 0; index < board.length; index += 1) {
    if (board[index]?.color === color) moves.push(...legalMovesForPiece(board, index))
  }
  return moves
}

export function applyBacklashMove(
  board: readonly (BacklashPiece | null)[],
  requested: { from: number; to: number },
  options: { jumpOnly?: boolean; excludedLandings?: ReadonlySet<number> } = {},
): BacklashAppliedMove | null {
  const move = legalMovesForPiece(board, requested.from, options)
    .find((candidate) => candidate.to === requested.to)
  if (!move) return null

  const movedPiece = board[move.from]
  if (!movedPiece) return null
  const next = board.map((entry) => entry ? { ...entry } : null)
  let capturedPiece: BacklashPiece | null = null
  next[move.from] = null
  if (movedPiece.kind === "underling" && move.isCapture) {
    capturedPiece = next[move.to]
  } else if (move.jumped !== null && move.isCapture) {
    capturedPiece = next[move.jumped]
    next[move.jumped] = null
  }
  next[move.to] = { ...movedPiece }

  const destinationRow = boardCoordinates(move.to).row
  const promotionRow = movedPiece.color === "white" ? BACKLASH_BOARD_SIZE - 1 : 0
  return {
    board: next,
    move,
    movedPiece: { ...movedPiece },
    capturedPiece: capturedPiece ? { ...capturedPiece } : null,
    promotionAvailable: movedPiece.kind === "underling" && destinationRow === promotionRow,
  }
}

export function promoteUnderling(
  board: readonly (BacklashPiece | null)[],
  index: number,
): BacklashBoard | null {
  if (!isBoardIndex(index)) return null
  const current = board[index]
  if (!current || current.kind !== "underling") return null
  const promotionRow = current.color === "white" ? BACKLASH_BOARD_SIZE - 1 : 0
  if (boardCoordinates(index).row !== promotionRow) return null
  const next = board.map((entry) => entry ? { ...entry } : null)
  next[index] = { ...current, kind: "overling" }
  return next
}

export function countPieces(
  board: readonly (BacklashPiece | null)[],
  color: BacklashColor,
  kind?: BacklashPieceKind,
): number {
  return board.reduce(
    (total, current) => total + Number(current?.color === color && (!kind || current.kind === kind)),
    0,
  )
}

export function positionKey(
  board: readonly (BacklashPiece | null)[],
  turn: BacklashColor,
): string {
  const cells = board.map((current) => {
    if (!current) return "-"
    const color = current.color === "white" ? "w" : "b"
    return `${color}${current.kind === "overling" ? "o" : "u"}`
  })
  return `${turn}:${cells.join(",")}`
}

export function encodeBacklashPiece(piece: BacklashPiece | null): string {
  return piece ? `${piece.id}|${piece.color}|${piece.kind}` : ""
}

export function decodeBacklashPiece(value: string): BacklashPiece | null {
  if (!value) return null
  const [id, color, kind, ...extra] = value.split("|")
  if (
    !id
    || extra.length > 0
    || (color !== "white" && color !== "black")
    || (kind !== "overling" && kind !== "underling")
  ) {
    return null
  }
  return { id, color, kind }
}
