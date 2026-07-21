// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from 'vitest'
import { BacklashRoomClient } from './BacklashRoomClient'

interface SentMessage {
  type: string
  payload: unknown
}

interface FakeRoom {
  calls: SentMessage[]
  send: (type: string, payload: unknown) => void
  leave: () => Promise<void>
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
})
