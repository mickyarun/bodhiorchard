// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { Client, getStateCallbacks, Room } from '@colyseus/sdk'
import type { ArraySchema, MapSchema } from '@colyseus/schema'
import {
  BACKLASH_BOARD_SIZE,
  decodeBacklashPiece,
  type BacklashBoard,
  type BacklashColor,
} from '@shared/minigames/backlash'
import {
  isBacklashEncouragement,
  type BacklashEncouragement,
} from '@shared/minigames/backlashSocial'
import { resolveColyseusUrl } from './colyseusUrl'

export type BacklashPhase = 'lobby' | 'playing' | 'jump' | 'promotion' | 'finished'

export interface BacklashPlayerSnapshot {
  userId: string
  name: string
  color: BacklashColor | null
  connected: boolean
  rematchReady: boolean
  capturedOverlings: number
}

export interface BacklashViewerSnapshot {
  userId: string
  name: string
}

export interface BacklashSnapshot {
  orgId: string
  hostUserId: string
  invitedUserId: string
  phase: BacklashPhase
  turnColor: BacklashColor
  turnUserId: string
  matchId: string
  winnerId: string
  outcome: '' | 'win' | 'draw' | 'forfeit'
  outcomeReason: string
  lockedJumpIndex: number
  pendingPromotionIndex: number
  revision: number
  moveCount: number
  turnDeadlineMs: number
  viewerCount: number
  board: BacklashBoard
  legalTargets: number[]
  players: BacklashPlayerSnapshot[]
  viewers: BacklashViewerSnapshot[]
}

export interface BacklashEncouragementEvent {
  id: string
  userId: string
  name: string
  reaction: BacklashEncouragement
  createdAtMs: number
}

export interface BacklashAuth {
  userId: string
  name: string
  orgId: string
  token?: string
}

interface RawPlayer {
  userId?: string
  name?: string
  color?: string
  connected?: boolean
  rematchReady?: boolean
  capturedOverlings?: number
}

interface RawViewer {
  userId?: string
  name?: string
}

interface BacklashStateShape {
  orgId?: string
  hostUserId?: string
  invitedUserId?: string
  phase?: string
  turnColor?: string
  turnUserId?: string
  matchId?: string
  winnerId?: string
  outcome?: string
  outcomeReason?: string
  lockedJumpIndex?: number
  pendingPromotionIndex?: number
  revision?: number
  moveCount?: number
  turnDeadlineMs?: number
  viewerCount?: number
  board: ArraySchema<string>
  legalTargets: ArraySchema<number>
  players: MapSchema<RawPlayer>
  viewers: MapSchema<RawViewer>
}

const RECONNECT_DELAYS_MS = [500, 1_500, 3_000, 5_000, 8_000] as const

export class BacklashRoomClient {
  private readonly client: Client
  private room: Room<BacklashStateShape> | null = null
  private stopped = false

  onStateChange: ((snapshot: BacklashSnapshot) => void) | null = null
  onConnectionChange: ((status: 'connected' | 'reconnecting' | 'disconnected') => void) | null = null
  onError: ((reason: string) => void) | null = null
  onClosed: ((reason: string) => void) | null = null
  onEncouragement: ((event: BacklashEncouragementEvent) => void) | null = null

  constructor(serverUrl?: string) {
    this.client = new Client(serverUrl ?? resolveColyseusUrl())
  }

  async joinById(roomId: string, auth: BacklashAuth): Promise<void> {
    await this.leave()
    this.stopped = false
    const room = await this.client.joinById<BacklashStateShape>(roomId, {
      userId: auth.userId,
      name: auth.name,
      orgId: auth.orgId,
      token: auth.token ?? '',
    })
    this.attachRoom(room)
  }

  sendMove(from: number, to: number, turnRevision: number): void {
    this.room?.send('backlash_move', { from, to, turnRevision })
  }

  sendEndJump(): void {
    this.room?.send('backlash_end_jump', {})
  }

  sendPromotion(accept: boolean): void {
    this.room?.send('backlash_promote', { accept })
  }

  sendRematch(): void {
    this.room?.send('backlash_rematch', {})
  }

  sendCancel(): void {
    this.room?.send('backlash_cancel', {})
  }

  sendEncouragement(reaction: BacklashEncouragement): void {
    this.room?.send('backlash_encourage', { reaction })
  }

  async leave(): Promise<void> {
    this.stopped = true
    const room = this.room
    this.room = null
    if (!room) return
    try {
      await room.leave()
    } catch {
      // A closed socket needs no additional cleanup.
    }
  }

  destroy(): void {
    void this.leave()
    this.onStateChange = null
    this.onConnectionChange = null
    this.onError = null
    this.onClosed = null
    this.onEncouragement = null
  }

  private attachRoom(room: Room<BacklashStateShape>): void {
    this.room = room
    this.onConnectionChange?.('connected')
    room.onMessage('backlash_error', (payload: { reason?: unknown }) => {
      this.onError?.(typeof payload.reason === 'string' ? payload.reason : 'invalid_action')
    })
    room.onMessage('backlash_closed', (payload: { reason?: unknown }) => {
      const reason = typeof payload.reason === 'string' ? payload.reason : 'room_closed'
      this.stopped = true
      this.room = null
      this.onConnectionChange?.('disconnected')
      this.onClosed?.(reason)
    })
    room.onMessage('backlash_encouragement', (payload: unknown) => {
      const event = parseBacklashEncouragementEvent(payload)
      if (event) this.onEncouragement?.(event)
    })
    this.wireState(room)
    const reconnectionToken = room.reconnectionToken
    room.onLeave((code) => {
      if (this.stopped || this.room !== room) return
      this.room = null
      if (code === 1000) {
        this.onConnectionChange?.('disconnected')
        return
      }
      void this.reconnect(reconnectionToken)
    })
  }

  private async reconnect(reconnectionToken: string): Promise<void> {
    this.onConnectionChange?.('reconnecting')
    for (const delayMs of RECONNECT_DELAYS_MS) {
      await wait(delayMs)
      if (this.stopped) return
      try {
        const room = await this.client.reconnect<BacklashStateShape>(reconnectionToken)
        if (this.stopped) {
          await room.leave()
          return
        }
        this.attachRoom(room)
        return
      } catch {
        // Retry within the server's 30-second reconnection window.
      }
    }
    if (!this.stopped) this.onConnectionChange?.('disconnected')
  }

  private wireState(room: Room<BacklashStateShape>): void {
    const $ = getStateCallbacks(room)
    const state = $(room.state)
    let publishPending = false
    const publishNow = (): void => {
      if (this.room === room) this.onStateChange?.(snapshotFromState(room.state))
    }
    const publish = (): void => {
      if (publishPending) return
      publishPending = true
      queueMicrotask(() => {
        publishPending = false
        publishNow()
      })
    }

    state.onChange(() => publish())
    state.board.onAdd(() => publish())
    state.board.onChange(() => publish())
    state.board.onRemove(() => publish())
    state.legalTargets.onAdd(() => publish())
    state.legalTargets.onChange(() => publish())
    state.legalTargets.onRemove(() => publish())
    state.players.onAdd((player: RawPlayer) => {
      publish()
      $(player).onChange(() => publish())
    }, true)
    state.players.onRemove(() => publish())
    state.viewers.onAdd((viewer: RawViewer) => {
      publish()
      $(viewer).onChange(() => publish())
    }, true)
    state.viewers.onRemove(() => publish())
    publishNow()
  }
}

function snapshotFromState(state: BacklashStateShape): BacklashSnapshot {
  const board: BacklashBoard = Array.from({ length: BACKLASH_BOARD_SIZE ** 2 }, (_, index) =>
    decodeBacklashPiece(state.board?.at(index) ?? ''),
  )
  const legalTargets: number[] = []
  state.legalTargets?.forEach((target) => legalTargets.push(target))
  const players: BacklashPlayerSnapshot[] = []
  state.players?.forEach((player) => players.push({
    userId: player.userId ?? '',
    name: player.name?.trim() || 'Player',
    color: toColor(player.color),
    connected: player.connected ?? false,
    rematchReady: player.rematchReady ?? false,
    capturedOverlings: player.capturedOverlings ?? 0,
  }))
  const viewers: BacklashViewerSnapshot[] = []
  state.viewers.forEach((viewer) => viewers.push({
    userId: viewer.userId ?? '',
    name: viewer.name?.trim() || 'Viewer',
  }))
  return {
    orgId: state.orgId ?? '',
    hostUserId: state.hostUserId ?? '',
    invitedUserId: state.invitedUserId ?? '',
    phase: toPhase(state.phase),
    turnColor: toColor(state.turnColor) ?? 'white',
    turnUserId: state.turnUserId ?? '',
    matchId: state.matchId ?? '',
    winnerId: state.winnerId ?? '',
    outcome: toOutcome(state.outcome),
    outcomeReason: state.outcomeReason ?? '',
    lockedJumpIndex: state.lockedJumpIndex ?? -1,
    pendingPromotionIndex: state.pendingPromotionIndex ?? -1,
    revision: state.revision ?? 0,
    moveCount: state.moveCount ?? 0,
    turnDeadlineMs: state.turnDeadlineMs ?? 0,
    viewerCount: viewers.length,
    board,
    legalTargets,
    players,
    viewers,
  }
}

export function parseBacklashEncouragementEvent(
  payload: unknown,
): BacklashEncouragementEvent | null {
  if (typeof payload !== 'object' || payload === null) return null
  const value = payload as Record<string, unknown>
  if (
    typeof value.id !== 'string'
    || typeof value.userId !== 'string'
    || typeof value.name !== 'string'
    || !isBacklashEncouragement(value.reaction)
    || typeof value.createdAtMs !== 'number'
    || !Number.isFinite(value.createdAtMs)
  ) return null
  return {
    id: value.id,
    userId: value.userId,
    name: value.name.slice(0, 120),
    reaction: value.reaction,
    createdAtMs: value.createdAtMs,
  }
}

function toColor(value: string | undefined): BacklashColor | null {
  return value === 'white' || value === 'black' ? value : null
}

function toPhase(value: string | undefined): BacklashPhase {
  return value === 'playing' || value === 'jump' || value === 'promotion' || value === 'finished'
    ? value
    : 'lobby'
}

function toOutcome(value: string | undefined): BacklashSnapshot['outcome'] {
  return value === 'win' || value === 'draw' || value === 'forfeit' ? value : ''
}

function wait(delayMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs))
}
