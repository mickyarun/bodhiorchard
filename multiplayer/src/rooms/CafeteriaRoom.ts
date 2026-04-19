// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaRoom — Colyseus room for the cafeteria interior.
 *
 * Room ID pattern: "cafeteria-{orgId}"
 * One shared room per org; every visitor joins the same room so the queue
 * and cooking state are globally consistent (mirrors CoffeeBarRoom).
 *
 * State:
 *   - players  — visitors currently inside (position/anim sync @ 20Hz)
 *   - queue    — ArraySchema<string> of userIds waiting (FIFO)
 *   - active   — the single in-progress order (phase-driven)
 *
 * Messages:
 *   "move"            → { x, z, yaw, animState } — visitor position @ 20Hz
 *   "cafe_enqueue"    → { meal }                 — join the line
 *   "cafe_leave_queue"→ {}                       — drop out of the line
 *   "cafe_ack_dispense"→ {}                      — take your meal
 *
 * Scope cut vs CoffeeBarRoom: no NPC bridge (`enqueueNpc`,
 * `onActiveChanged`). Cafeteria V1 is player-only; OrgRoom does not
 * enqueue simulated diners. Add the bridge when NPC diners are needed.
 */
import { Room, Client } from "colyseus"
import { PlayerState } from "../schema/PlayerState"
import { CafeteriaState } from "../schema/CafeteriaState"
import { isCafeteriaMeal } from "../sim/CafeteriaMenu"
import {
  advancePhase,
  acknowledgeDispense,
  type PhaseSnapshot,
  type QueueEntry,
} from "../sim/CafeteriaPhase"

const SIM_TICK_MS = 50
const MIN_MOVE_INTERVAL_MS = 25

const VALID_ANIMS = new Set([
  "idle",
  "walk",
  "sit",
  "sleep",
  "cook",
  "eat",
])

interface CafeteriaJoinOptions {
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
  meal: string
}

export class CafeteriaRoom extends Room<{ state: CafeteriaState }> {
  maxClients = 20

  private lastMoveMs = new Map<string, number>()

  /** Meal chosen by each queued userId, kept alongside state.queue (which
   *  only stores userIds because schema arrays must be homogeneous). */
  private pendingMeals = new Map<string, string>()

  /** userId → sessionId lookup for "queue your own userId" validation. */
  private sessionByUserId = new Map<string, string>()

  onCreate(options: { orgId?: string }) {
    const state = new CafeteriaState()
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

    this.onMessage("cafe_enqueue", (client, data: EnqueueMessage) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      if (!isCafeteriaMeal(data?.meal)) return
      this.enqueueInternal(player.userId, data.meal)
    })

    this.onMessage("cafe_leave_queue", (client) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      this.leaveQueue(player.userId)
    })

    this.onMessage("cafe_ack_dispense", (client) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      const result = acknowledgeDispense(this.snapshotActive(), player.userId, Date.now())
      if (result.next) this.applyPhaseResult(result)
    })

    this.setSimulationInterval((_dt) => this.tick(), SIM_TICK_MS)
  }

  onJoin(client: Client, options: CafeteriaJoinOptions) {
    const player = new PlayerState()
    player.userId = options.userId || client.sessionId
    player.name = options.name || "Visitor"
    player.characterModel = options.characterModel || ""
    player.connected = true
    this.state.players.set(client.sessionId, player)
    this.sessionByUserId.set(player.userId, client.sessionId)
    console.log(`[CafeteriaRoom] ${player.name} (${client.sessionId}) joined`)
  }

  onLeave(client: Client) {
    const player = this.state.players.get(client.sessionId)
    if (player) {
      this.sessionByUserId.delete(player.userId)
      this.leaveQueue(player.userId)
      if (this.state.active.userId === player.userId) {
        this.resetActiveToIdle()
      }
    }
    this.state.players.delete(client.sessionId)
    this.lastMoveMs.delete(client.sessionId)
  }

  onDispose() {
    console.log(`[CafeteriaRoom] Room ${this.roomId} disposed`)
  }

  private enqueueInternal(userId: string, meal: string): void {
    if (this.state.active.userId === userId) return
    if (this.state.queue.indexOf(userId) !== -1) return
    this.state.queue.push(userId)
    this.pendingMeals.set(userId, meal)
  }

  private leaveQueue(userId: string): void {
    const idx = this.state.queue.indexOf(userId)
    if (idx === -1) return
    this.state.queue.splice(idx, 1)
    this.pendingMeals.delete(userId)
  }

  private resetActiveToIdle(): void {
    this.state.active.phase = "idle"
    this.state.active.userId = ""
    this.state.active.meal = ""
    this.state.active.phaseStartMs = Date.now()
  }

  private snapshotActive(): PhaseSnapshot {
    const a = this.state.active
    return {
      phase: a.phase as PhaseSnapshot["phase"],
      phaseStartMs: a.phaseStartMs,
      userId: a.userId,
      meal: a.meal,
    }
  }

  private peekQueueHead(): QueueEntry | null {
    if (this.state.queue.length === 0) return null
    const userId = this.state.queue[0]
    const meal = this.pendingMeals.get(userId)
    if (!meal) {
      this.state.queue.splice(0, 1)
      return null
    }
    return { userId, meal }
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

    if (result.dequeued > 0) {
      const userId = this.state.queue.shift()
      if (userId) this.pendingMeals.delete(userId)
    }

    this.state.active.phase = next.phase
    this.state.active.phaseStartMs = next.phaseStartMs
    this.state.active.userId = next.userId
    this.state.active.meal = next.meal
  }
}
