// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from 'vitest'
import { activeBacklashToSnapshot } from './OrgRoomClient'

describe('activeBacklashToSnapshot', () => {
  it('copies a Colyseus summary into an immutable-friendly plain snapshot', () => {
    const participantUserIds = { 0: 'host', 1: 'invitee', length: 2 }

    expect(activeBacklashToSnapshot({
      roomId: 'room-1',
      hostUserId: 'host',
      hostName: ' Alice ',
      invitedName: ' Bob ',
      phase: 'playing',
      viewerCount: 2,
      viewerNames: { 0: ' Sam ', 1: ' Jo ', length: 2 },
      participantUserIds,
    })).toEqual({
      roomId: 'room-1',
      hostUserId: 'host',
      hostName: 'Alice',
      invitedName: 'Bob',
      phase: 'playing',
      viewerCount: 2,
      viewerNames: ['Sam', 'Jo'],
      participantUserIds: ['host', 'invitee'],
    })
  })

  it('uses safe display defaults for incomplete hydration', () => {
    expect(activeBacklashToSnapshot({})).toEqual({
      roomId: '',
      hostUserId: '',
      hostName: 'Player',
      invitedName: 'Opponent',
      phase: 'lobby',
      viewerCount: 0,
      viewerNames: [],
      participantUserIds: [],
    })
  })
})
