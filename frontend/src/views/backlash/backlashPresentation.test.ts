// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from 'vitest'
import {
  boardIndex,
  createBacklashBoard,
} from '@shared/minigames/backlash'
import {
  findCapturedBacklashPieces,
  findRemovedBacklashPieces,
} from './backlashPresentation'

describe('Backlash presentation state', () => {
  it('identifies the exact piece and square removed by a capture', () => {
    const previous = createBacklashBoard()
    const next = previous.map((piece) => piece ? { ...piece } : null)
    const capturedIndex = boardIndex(6, 2)
    const capturedPiece = next[capturedIndex]
    next[capturedIndex] = null

    expect(findCapturedBacklashPieces(previous, next)).toEqual([
      { index: capturedIndex, piece: capturedPiece },
    ])
  })

  it('does not mistake a normal move for a capture', () => {
    const previous = createBacklashBoard()
    const next = previous.map((piece) => piece ? { ...piece } : null)
    const origin = boardIndex(1, 0)
    const destination = boardIndex(2, 0)
    next[destination] = next[origin]
    next[origin] = null

    expect(findCapturedBacklashPieces(previous, next)).toEqual([])
  })

  it('lists currently removed pieces by side', () => {
    const board = createBacklashBoard()
    const removedIndex = boardIndex(7, 3)
    const removedPiece = board[removedIndex]
    board[removedIndex] = null

    expect(findRemovedBacklashPieces(board, 'black')).toEqual([removedPiece])
    expect(findRemovedBacklashPieces(board, 'white')).toEqual([])
  })

  it('returns empty presentation data before a complete board is hydrated', () => {
    expect(findCapturedBacklashPieces(undefined, [])).toEqual([])
    expect(findRemovedBacklashPieces([], 'white')).toEqual([])
    expect(findRemovedBacklashPieces(createBacklashBoard(), null)).toEqual([])
  })
})
