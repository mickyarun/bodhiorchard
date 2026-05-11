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
 * CoffeeBarRoom — Colyseus room for the coffee bar interior.
 *
 * Room ID pattern: "coffeebar-{orgId}"
 * One shared room per org. All visitors (from any house or garden) join the
 * same room so the queue and brewing state are globally consistent.
 *
 * State:
 *   - players    — visitors currently inside (position/anim sync @ 20Hz)
 *   - queue      — ArraySchema<string> of userIds waiting (FIFO)
 *   - active     — the single in-progress order (phase-driven)
 *
 * Messages:
 *   "move"               → { x, z, yaw, animState } — visitor position @ 20Hz
 *   "coffee_enqueue"     → { drink }               — join the line
 *   "coffee_leave_queue" → {}                      — drop out of the line
 *   "coffee_ack_dispense"→ {}                      — take your drink; advances phase
 *
 * NPC bridge (same-process calls from OrgRoom):
 *   enqueueNpc(npcUserId, drink)  — enqueue a simulated character
 *   onActiveChanged(listener)     — subscribe to active-phase transitions
 */
import { Room, Client } from "colyseus"
import { PlayerState } from "../schema/PlayerState"
import { CoffeeBarState, CoffeeAction } from "../schema/CoffeeBarState"
import { isCoffeeDrink } from "../sim/CoffeeMenu"
import {
  advancePhase,
  acknowledgeDispense,
  type PhaseSnapshot,
  type QueueEntry,
} from "../sim/CoffeeBarPhase"

// 20Hz matches the OrgRoom cadence and Colyseus default state sync.
const SIM_TICK_MS = 50

const MIN_MOVE_INTERVAL_MS = 25

const VALID_ANIMS = new Set([
  "idle",
  "walk",
  "sit",
  "sleep",
  "brew",
  "drink",
])

interface CoffeeBarJoinOptions {
  userId: string
  name: string
  characterModel?: string
}

interface MoveMessage {
  x: number
  z: number
  yaw: number
  animState: string
}

interface EnqueueMessage {
  drink: string
}

/**
 * Listener payload emitted when the active action transitions.
 * Used by the NPC bridge (OrgRoom) to return NPCs to their seats.
 */
export interface ActiveChangedEvent {
  userId: string
  drink: string
  phase: PhaseSnapshot["phase"]
  justDispensed: boolean
  justCompleted: boolean
}

export class CoffeeBarRoom extends Room<{ state: CoffeeBarState }> {
  maxClients = 20

  // Per-session move throttle timestamps
  private lastMoveMs = new Map<string, number>()

  // Pending drink chosen by each queued userId, indexed alongside state.queue.
  // state.queue only stores userIds (schema arrays must be homogeneous), so we
  // keep drink selections in a side map. NPC drinks live here too.
  private pendingDrinks = new Map<string, string>()

  // Map userId → sessionId for enforcing "queue your own userId" and for
  // looking up clients when a real player's drink is ready.
  private sessionByUserId = new Map<string, string>()

  private activeListeners: Array<(event: ActiveChangedEvent) => void> = []

  onCreate(options: { orgId?: string }) {
    const state = new CoffeeBarState()
    if (options.orgId) state.orgId = options.orgId
    this.setState(state)

    this.onMessage("move", (client, data: MoveMessage) => {
      const now = Date.now()
      const last = this.lastMoveMs.get(client.sessionId) ?? 0
      if (now - last < MIN_MOVE_INTERVAL_MS) return
      this.lastMoveMs.set(client.sessionId, now)

      const player = this.state.players.get(client.sessionId)
      if (!player) return
      if (!Number.isFinite(data?.x) || !Number.isFinite(data?.z)) return
      if (!Number.isFinite(data?.yaw)) return
      if (!VALID_ANIMS.has(data.animState)) return
      player.x = data.x
      player.z = data.z
      player.yaw = data.yaw
      player.animState = data.animState
    })

    this.onMessage("coffee_enqueue", (client, data: EnqueueMessage) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      if (!isCoffeeDrink(data?.drink)) return
      this.enqueueInternal(player.userId, data.drink)
    })

    this.onMessage("coffee_leave_queue", (client) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      this.leaveQueue(player.userId)
    })

    this.onMessage("coffee_ack_dispense", (client) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      const result = acknowledgeDispense(this.snapshotActive(), player.userId, Date.now())
      if (result.next) this.applyPhaseResult(result)
    })

    this.setSimulationInterval((_dt) => this.tick(), SIM_TICK_MS)
  }

  onJoin(client: Client, options: CoffeeBarJoinOptions) {
    const player = new PlayerState()
    player.userId = options.userId || client.sessionId
    player.name = options.name || "Visitor"
    player.characterModel = options.characterModel || ""
    player.connected = true
    this.state.players.set(client.sessionId, player)
    this.sessionByUserId.set(player.userId, client.sessionId)
    console.log(`[CoffeeBarRoom] ${player.name} (${client.sessionId}) joined`)
  }

  onLeave(client: Client) {
    const player = this.state.players.get(client.sessionId)
    if (player) {
      this.sessionByUserId.delete(player.userId)
      // Drop out of queue if they were waiting
      this.leaveQueue(player.userId)
      // If they were being served, abort that action
      if (this.state.active.userId === player.userId) {
        this.resetActiveToIdle()
      }
    }
    this.state.players.delete(client.sessionId)
    this.lastMoveMs.delete(client.sessionId)
  }

  onDispose() {
    console.log(`[CoffeeBarRoom] Room ${this.roomId} disposed`)
    this.activeListeners = []
  }

  // ── NPC bridge API ────────────────────────────────────────────────

  /** Enqueue a simulated NPC. userId should use the "npc:{id}" prefix. */
  enqueueNpc(npcUserId: string, drink: string): void {
    if (!isCoffeeDrink(drink)) return
    this.enqueueInternal(npcUserId, drink)
  }

  /** Subscribe to active-phase transitions. Returns an unsubscribe fn. */
  onActiveChanged(listener: (event: ActiveChangedEvent) => void): () => void {
    this.activeListeners.push(listener)
    return () => {
      this.activeListeners = this.activeListeners.filter(l => l !== listener)
    }
  }

  // ── Internal helpers ──────────────────────────────────────────────

  private enqueueInternal(userId: string, drink: string): void {
    // Dedupe: if already queued or currently active, ignore.
    if (this.state.active.userId === userId) return
    if (this.state.queue.indexOf(userId) !== -1) return
    this.state.queue.push(userId)
    this.pendingDrinks.set(userId, drink)
  }

  private leaveQueue(userId: string): void {
    const idx = this.state.queue.indexOf(userId)
    if (idx === -1) return
    this.state.queue.splice(idx, 1)
    this.pendingDrinks.delete(userId)
  }

  private resetActiveToIdle(): void {
    this.state.active.phase = "idle"
    this.state.active.userId = ""
    this.state.active.drink = ""
    this.state.active.phaseStartMs = Date.now()
  }

  private snapshotActive(): PhaseSnapshot {
    const a = this.state.active
    return {
      phase: a.phase as PhaseSnapshot["phase"],
      phaseStartMs: a.phaseStartMs,
      userId: a.userId,
      drink: a.drink,
    }
  }

  private peekQueueHead(): QueueEntry | null {
    if (this.state.queue.length === 0) return null
    const userId = this.state.queue[0]
    const drink = this.pendingDrinks.get(userId)
    if (!drink) {
      // Orphaned entry — drop it so the queue can progress.
      this.state.queue.splice(0, 1)
      return null
    }
    return { userId, drink }
  }

  private tick(): void {
    const result = advancePhase(this.snapshotActive(), this.peekQueueHead(), Date.now())
    if (result.next) this.applyPhaseResult(result)
  }

  private applyPhaseResult(result: {
    next: PhaseSnapshot | null
    dequeued: number
    justDispensed: boolean
    justCompleted: boolean
  }): void {
    const next = result.next
    if (!next) return

    // Pop the consumed queue entry
    if (result.dequeued > 0) {
      const userId = this.state.queue.shift()
      if (userId) this.pendingDrinks.delete(userId)
    }

    this.state.active.phase = next.phase
    this.state.active.phaseStartMs = next.phaseStartMs
    this.state.active.userId = next.userId
    this.state.active.drink = next.drink

    const event: ActiveChangedEvent = {
      userId: next.userId,
      drink: next.drink,
      phase: next.phase,
      justDispensed: result.justDispensed,
      justCompleted: result.justCompleted,
    }
    for (const listener of this.activeListeners) {
      try {
        listener(event)
      } catch (err) {
        console.error("[CoffeeBarRoom] active listener threw", err)
      }
    }
  }
}
