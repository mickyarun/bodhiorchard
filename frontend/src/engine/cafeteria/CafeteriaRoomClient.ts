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
 * CafeteriaRoomClient — thin subscription wrapper around the Colyseus
 * CafeteriaRoom state. Mirrors CoffeeBarRoomClient with meal-oriented
 * renames (drink → meal, brewing → cooking).
 */
import type { Room } from '@colyseus/sdk'
import { ColyseusClient } from '../../multiplayer'
import type { PlayerData } from '../../multiplayer/ColyseusClient'

export interface CafeteriaActionSnapshot {
  userId: string
  meal: string
  phase: string
  phaseStartMs: number
}

export interface CafeteriaSnapshot {
  active: CafeteriaActionSnapshot
  queue: string[]
}

type Listener = (snap: CafeteriaSnapshot) => void

interface RawCafeteriaState {
  active?: CafeteriaActionSnapshot
  queue?: { toArray?: () => string[] } & Iterable<string>
  players?: Iterable<[string, RawCafeteriaPlayer]> & { forEach?: (cb: (p: RawCafeteriaPlayer, key: string) => void) => void }
}

interface RawCafeteriaPlayer {
  userId?: string
  name?: string
  characterModel?: string
  x?: number
  z?: number
  yaw?: number
  animState?: string
}

export class CafeteriaRoomClient {
  private room: Room | null = null
  private listeners: Listener[] = []
  private latest: CafeteriaSnapshot = {
    active: { userId: '', meal: '', phase: 'idle', phaseStartMs: 0 },
    queue: [],
  }
  private playersBySession = new Map<string, PlayerData>()

  async connect(
    orgId: string,
    user: { userId: string; name: string; characterModel?: string },
  ): Promise<void> {
    const client = ColyseusClient.getInstance()
    this.room = await client.joinCafeteriaRoom(orgId, user)
    this.room.onStateChange((state: unknown) => this.onStateChange(state as RawCafeteriaState))
  }

  get snapshot(): CafeteriaSnapshot { return this.latest }

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

  /** Send a meal order. Server validates the meal whitelist. */
  enqueueMeal(meal: string): void {
    ColyseusClient.getInstance().sendCafeteriaEnqueue(meal)
  }

  leaveQueue(): void {
    ColyseusClient.getInstance().sendCafeteriaLeaveQueue()
  }

  /** Ack that the meal was taken — advances phase dispensed -> idle. */
  ackDispense(): void {
    ColyseusClient.getInstance().sendCafeteriaAckDispense()
  }

  sendMove(x: number, z: number, yaw: number, animState: string): void {
    ColyseusClient.getInstance().sendMove(x, z, yaw, animState)
  }

  getPlayers(): PlayerData[] {
    return Array.from(this.playersBySession.values())
  }

  private onStateChange(state: RawCafeteriaState): void {
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
        meal: active?.meal ?? '',
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
        console.error('[CafeteriaRoomClient] listener threw', err)
      }
    }
  }

  private refreshPlayers(
    players: RawCafeteriaState['players'] | undefined,
  ): void {
    this.playersBySession.clear()
    if (!players) return

    const ingest = (raw: RawCafeteriaPlayer, sessionId: string): void => {
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

    if (typeof players.forEach === 'function') {
      players.forEach((raw, sessionId) => ingest(raw, sessionId))
    } else {
      for (const [sessionId, raw] of players) ingest(raw, sessionId)
    }
  }
}
