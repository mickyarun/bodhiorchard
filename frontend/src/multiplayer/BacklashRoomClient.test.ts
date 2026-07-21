// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it, vi } from 'vitest'
import { BACKLASH_BOARD_SIZE, boardIndex } from '@shared/minigames/backlash'
import { BacklashRoomClient } from './BacklashRoomClient'

const { getStateCallbacksMock } = vi.hoisted(() => ({
  getStateCallbacksMock: vi.fn(),
}))

vi.mock('@colyseus/sdk', () => ({
  Client: class Client {},
  Room: class Room {},
  getStateCallbacks: getStateCallbacksMock,
}))

interface SentMessage {
  type: string
  payload: unknown
}

interface FakeRoom {
  calls: SentMessage[]
  send: (type: string, payload: unknown) => void
  leave: () => Promise<void>
}

interface CollectionListeners {
  onAdd: ReturnType<typeof vi.fn>
  onChange: ReturnType<typeof vi.fn>
  onRemove: ReturnType<typeof vi.fn>
}

function fakeRoom(): FakeRoom {
  const calls: SentMessage[] = []
  return {
    calls,
    send: (type, payload) => calls.push({ type, payload }),
    leave: () => Promise.resolve(),
  }
}

function withRoom(client: BacklashRoomClient, room: FakeRoom): void {
  ;(client as unknown as { room: FakeRoom }).room = room
}

function collectionListeners(): CollectionListeners {
  return {
    onAdd: vi.fn(),
    onChange: vi.fn(),
    onRemove: vi.fn(),
  }
}

describe('BacklashRoomClient message contracts', () => {
  it('sends a revision-guarded move payload', () => {
    const client = new BacklashRoomClient('ws://test')
    const room = fakeRoom()
    withRoom(client, room)

    client.sendMove(9, 17, 4)

    expect(room.calls).toEqual([
      { type: 'backlash_move', payload: { from: 9, to: 17, turnRevision: 4 } },
    ])
  })

  it('sends the remaining action payloads without client-owned state', () => {
    const client = new BacklashRoomClient('ws://test')
    const room = fakeRoom()
    withRoom(client, room)

    client.sendEndJump()
    client.sendPromotion(true)
    client.sendPromotion(false)
    client.sendRematch()
    client.sendCancel()

    expect(room.calls).toEqual([
      { type: 'backlash_end_jump', payload: {} },
      { type: 'backlash_promote', payload: { accept: true } },
      { type: 'backlash_promote', payload: { accept: false } },
      { type: 'backlash_rematch', payload: {} },
      { type: 'backlash_cancel', payload: {} },
    ])
  })

  it('does not send when no room is attached', () => {
    const client = new BacklashRoomClient('ws://test')

    expect(() => {
      client.sendMove(0, 1, 0)
      client.sendEndJump()
      client.sendPromotion(true)
      client.sendRematch()
      client.sendCancel()
    }).not.toThrow()
  })

  it('publishes one complete snapshot after all piece replacements are decoded', async () => {
    const board = Array<string>(BACKLASH_BOARD_SIZE ** 2).fill('')
    const origin = boardIndex(1, 1)
    const destination = boardIndex(2, 1)
    board[origin] = 'white-underling-1|white|underling'
    const state = {
      phase: 'playing',
      turnColor: 'white',
      board,
      legalTargets: [] as number[],
      players: new Map(),
    }
    const boardListeners = collectionListeners()
    const legalTargetListeners = collectionListeners()
    const stateListeners = {
      onChange: vi.fn(),
      board: boardListeners,
      legalTargets: legalTargetListeners,
      players: collectionListeners(),
    }
    getStateCallbacksMock.mockReturnValue((target: unknown) => (
      target === state ? stateListeners : { onChange: vi.fn() }
    ))
    const room = { state }
    const client = new BacklashRoomClient('ws://test')
    const snapshots = vi.fn()
    client.onStateChange = snapshots
    ;(client as unknown as { room: unknown }).room = room

    ;(client as unknown as { wireState: (value: unknown) => void }).wireState(room)
    snapshots.mockClear()

    board[origin] = ''
    const onBoardChange = boardListeners.onChange.mock.calls[0]?.[0] as (() => void) | undefined
    onBoardChange?.()
    expect(snapshots).not.toHaveBeenCalled()

    board[destination] = 'white-underling-1|white|underling'
    onBoardChange?.()
    await Promise.resolve()

    expect(boardListeners.onChange).toHaveBeenCalledOnce()
    expect(legalTargetListeners.onChange).toHaveBeenCalledOnce()
    expect(snapshots).toHaveBeenCalledOnce()
    const snapshot = snapshots.mock.calls[0]?.[0]
    expect(snapshot.board[origin]).toBeNull()
    expect(snapshot.board[destination]).toEqual({
      id: 'white-underling-1',
      color: 'white',
      kind: 'underling',
    })
  })
})
