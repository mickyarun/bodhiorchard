// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import {
  BACKLASH_BOARD_SIZE,
  createBacklashBoard,
  type BacklashBoard,
  type BacklashColor,
  type BacklashPiece,
} from '@shared/minigames/backlash'

export interface RemovedBacklashPiece {
  index: number
  piece: BacklashPiece
}

const BOARD_CELL_COUNT = BACKLASH_BOARD_SIZE ** 2
const STARTING_PIECES = createBacklashBoard().filter(
  (piece): piece is BacklashPiece => piece !== null,
)

export function findCapturedBacklashPieces(
  previousBoard: BacklashBoard | undefined,
  nextBoard: BacklashBoard,
): RemovedBacklashPiece[] {
  if (!previousBoard || previousBoard.length !== BOARD_CELL_COUNT || nextBoard.length !== BOARD_CELL_COUNT) {
    return []
  }
  const nextIds = new Set(nextBoard.flatMap((piece) => piece ? [piece.id] : []))
  return previousBoard.flatMap((piece, index) => (
    piece && !nextIds.has(piece.id) ? [{ index, piece }] : []
  ))
}

export function findRemovedBacklashPieces(
  board: BacklashBoard | undefined,
  color: BacklashColor | null | undefined,
): BacklashPiece[] {
  if (!color || board?.length !== BOARD_CELL_COUNT) return []
  const activeIds = new Set(board.flatMap((piece) => piece ? [piece.id] : []))
  return STARTING_PIECES.filter((piece) => piece.color === color && !activeIds.has(piece.id))
}
