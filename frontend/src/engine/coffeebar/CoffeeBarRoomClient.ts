// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CoffeeBarRoomClient — thin subscription wrapper around the Colyseus
 * CoffeeBarRoom state. Mirrors the "just read what we need" shape of
 * OrgRoomClient: register listeners, get typed snapshots, don't leak
 * Colyseus internals to callers.
 *
 * Responsibilities:
 *   - Join via ColyseusClient.joinCoffeeBarRoom
 *   - Expose active-phase + queue snapshots (Phase 3)
 *   - Expose remote-player snapshots for rendering (Phase 5)
 *   - Forward move messages to the server (Phase 5)
 */
import type { Room } from '@colyseus/sdk'
import { ColyseusClient } from '../../multiplayer'
import type { PlayerData } from '../../multiplayer/ColyseusClient'

export interface CoffeeActionSnapshot {
  userId: string
  drink: string
  phase: string
  phaseStartMs: number
}

export interface CoffeeBarSnapshot {
  active: CoffeeActionSnapshot
  queue: string[]
}

type Listener = (snap: CoffeeBarSnapshot) => void

interface RawCoffeeState {
  active?: CoffeeActionSnapshot
  queue?: { toArray?: () => string[] } & Iterable<string>
  players?: Iterable<[string, RawCoffeePlayer]> & { forEach?: (cb: (p: RawCoffeePlayer, key: string) => void) => void }
}

interface RawCoffeePlayer {
  userId?: string
  name?: string
  characterModel?: string
  x?: number
  z?: number
  yaw?: number
  animState?: string
}

export class CoffeeBarRoomClient {
  private room: Room | null = null
  private listeners: Listener[] = []
  private latest: CoffeeBarSnapshot = {
    active: { userId: '', drink: '', phase: 'idle', phaseStartMs: 0 },
    queue: [],
  }
  /** Remote-player snapshots, keyed by sessionId. Refreshed on every state sync. */
  private playersBySession = new Map<string, PlayerData>()

  async connect(
    orgId: string,
    user: { userId: string; name: string; characterModel?: string },
  ): Promise<void> {
    const client = ColyseusClient.getInstance()
    this.room = await client.joinCoffeeBarRoom(orgId, user)
    this.room.onStateChange((state: unknown) => this.onStateChange(state as RawCoffeeState))
  }

  /** Current snapshot. Safe to read anytime after connect(). */
  get snapshot(): CoffeeBarSnapshot { return this.latest }

  /** Register a listener. Returns an unsubscribe function. */
  subscribe(listener: Listener): () => void {
    this.listeners.push(listener)
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener)
    }
  }

  async disconnect(): Promise<void> {
    this.listeners = []
    this.room = null
    await ColyseusClient.getInstance().leaveRoom().catch(() => {
      // Already disconnected — safe to ignore
    })
  }

  /** Send a coffee order. Server validates drink whitelist. */
  enqueueDrink(drink: string): void {
    ColyseusClient.getInstance().sendCoffeeEnqueue(drink)
  }

  /** Drop out of the queue (ignored server-side if already being served). */
  leaveQueue(): void {
    ColyseusClient.getInstance().sendCoffeeLeaveQueue()
  }

  /** Ack that the drink was taken — advances phase dispensed -> idle. */
  ackDispense(): void {
    ColyseusClient.getInstance().sendCoffeeAckDispense()
  }

  /** Broadcast the local player's position. Called ~20Hz from the update loop. */
  sendMove(x: number, z: number, yaw: number, animState: string): void {
    ColyseusClient.getInstance().sendMove(x, z, yaw, animState)
  }

  /**
   * Current remote-player snapshots (includes the local player — the caller
   * filters by userId). Returns a fresh array; safe to iterate without
   * worrying about concurrent mutation mid-frame.
   */
  getPlayers(): PlayerData[] {
    return Array.from(this.playersBySession.values())
  }

  private onStateChange(state: RawCoffeeState): void {
    const active = state.active
    const queueSrc = state.queue
    const queue: string[] = queueSrc?.toArray
      ? queueSrc.toArray()
      : queueSrc
      ? Array.from(queueSrc)
      : []

    this.latest = {
      active: {
        userId: active?.userId ?? '',
        drink: active?.drink ?? '',
        phase: active?.phase ?? 'idle',
        phaseStartMs: active?.phaseStartMs ?? 0,
      },
      queue,
    }

    this.refreshPlayers(state.players)

    for (const listener of this.listeners) {
      try {
        listener(this.latest)
      } catch (err) {
        console.error('[CoffeeBarRoomClient] listener threw', err)
      }
    }
  }

  private refreshPlayers(
    players: RawCoffeeState['players'] | undefined,
  ): void {
    this.playersBySession.clear()
    if (!players) return

    const ingest = (raw: RawCoffeePlayer, sessionId: string): void => {
      if (!raw.userId) return
      this.playersBySession.set(sessionId, {
        userId: raw.userId,
        name: raw.name ?? '',
        characterModel: raw.characterModel ?? '',
        x: raw.x ?? 0,
        z: raw.z ?? 0,
        yaw: raw.yaw ?? 0,
        animState: raw.animState ?? 'idle',
      })
    }

    // Colyseus MapSchema exposes `.forEach((value, key) => …)`; fall back to
    // iterable [key, value] tuples for resilience against SDK internals.
    if (typeof players.forEach === 'function') {
      players.forEach((raw, sessionId) => ingest(raw, sessionId))
    } else {
      for (const [sessionId, raw] of players) ingest(raw, sessionId)
    }
  }
}
