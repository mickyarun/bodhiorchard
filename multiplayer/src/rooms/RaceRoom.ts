// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RaceRoom — authoritative Colyseus room for one race-v2 instance.
 *
 * Lifecycle:
 *   onCreate: seeds `RaceRoomState` from options passed by OrgRoom when
 *             the host fires `race_create`. `phase` starts as 'lobby'.
 *   onJoin:   adds/updates a `RacerState` via `race_join` messages.
 *   tick:     at 20Hz during `running`, advances `RacePhysics`, checks
 *             finish conditions, fires the `finished` transition.
 *   onDispose: POSTs final placings to the backend via `BackendClient`.
 *
 * Size budget: this file must stay under 300 lines (hard cap). Input
 * validation and FSM wiring moved to `RaceRoomHelpers.ts` to keep that.
 */
import { Room, Client } from "colyseus"
import {
  COUNTDOWN_MS,
  MAX_RACERS,
  MIN_RACERS,
  RUNNING_TIMEOUT_MS,
  ALLOWED_DISTANCES_M,
  TICK_MS,
} from "../../../shared/race/RaceConstants"
import {
  type Racer,
  checkFinish,
  makeRacer,
  setMoving,
  tick as physicsTick,
  triggerSprintTap,
} from "../../../shared/race/RacePhysics"
import type { Placing } from "../../../shared/race/types"
import { RaceRoomState } from "../schema/RaceRoomState"
import { RacerState } from "../schema/RacerState"
import { PlacingState } from "../schema/PlacingState"
import {
  assertRaceCreateOptions,
  buildRacerState,
  copyRacerToSchema,
  type RaceCreateOptions,
} from "./RaceRoomHelpers"
import { postRaceResults } from "../bridge/BackendClient"
import { fireRaceDispose, fireRacePhase } from "../bridge/RaceRegistry"

const SIM_TICK_MS = TICK_MS

export class RaceRoom extends Room<{ state: RaceRoomState }> {
  maxClients = MAX_RACERS * 2 // racers + spectators

  /** In-memory physics mirror — schema state is updated from this each tick. */
  private physicsRacers: Racer[] = []
  private simHandle: NodeJS.Timeout | null = null
  /** Wall-clock at which running phase began (used to compute elapsedMs). */
  private runningStartedAtMs = 0

  onCreate(rawOptions: unknown): void {
    const options = assertRaceCreateOptions(rawOptions, ALLOWED_DISTANCES_M)
    this.seedState(options)
    this.registerHandlers()
  }

  onJoin(client: Client, options: { userId: string; name: string; characterModel?: string }): void {
    console.log(`[RaceRoom ${this.roomId}] ${options.name} (${client.sessionId}) joined`)
  }

  onLeave(client: Client): void {
    // Lobby leavers drop out of the racer roster; mid-race leavers keep their
    // slot but get `connected=false` so the client HUD can show ghost status.
    for (const racer of this.state.racers.values()) {
      if (racer.userId && this.clients.find((c) => c.sessionId === client.sessionId) === undefined) {
        if (racer.connected) racer.connected = false
      }
    }
  }

  onDispose(): void {
    this.stopSim()
    // Notify OrgRoom (if any) so it can drop our ActiveRaceSummary.
    fireRaceDispose(this.roomId)
    const placings = Array.from(this.state.placings)
    if (placings.length === 0) return

    const hasAnyFinisher = placings.some((p) => p.finished)
    if (!hasAnyFinisher) {
      console.log(`[RaceRoom ${this.roomId}] disposed with no finishers — skipping results POST`)
      return
    }

    // Fire-and-forget — Colyseus cannot await dispose. Network failures here
    // do NOT roll back local state; the bridge is expected to retry on 5xx.
    postRaceResults({
      roomId: this.roomId,
      orgId: this.state.orgId,
      hostUserId: this.state.hostUserId,
      distanceM: this.state.distanceM,
      placings: placings.map((p) => ({
        userId: p.racerId,
        finishTimeMs: p.finished ? p.finishTimeMs : null,
        place: p.place,
        finished: p.finished,
        distanceMReached: p.distanceM,
        distanceM: this.state.distanceM,
      })),
    }).catch((err: unknown) => {
      console.error(`[RaceRoom ${this.roomId}] postRaceResults failed:`, err)
    })
  }

  // ─── setup ───────────────────────────────

  private seedState(opts: RaceCreateOptions): void {
    const state = new RaceRoomState()
    state.orgId = opts.orgId
    state.hostUserId = opts.hostUserId
    state.hostName = opts.hostName
    state.distanceM = opts.distanceM
    state.phase = "lobby"
    state.phaseStartMs = Date.now()
    for (const id of opts.invitedUserIds) state.invitedUserIds.push(id)
    this.setState(state)
  }

  private registerHandlers(): void {
    this.onMessage("race_join", (client, data: unknown) => this.handleJoin(client, data))
    this.onMessage("race_start", (client) => this.handleStart(client))
    this.onMessage("race_move", (_client, data: unknown) => this.handleMove(data))
    this.onMessage("race_sprint_tap", (_client, data: unknown) => this.handleSprintTap(data))
  }

  // ─── message handlers ────────────────────

  private handleJoin(
    client: Client,
    raw: unknown,
  ): void {
    if (this.state.phase !== "lobby") return
    if (this.state.racers.size >= MAX_RACERS) return
    const r = buildRacerState(raw, this.state.racers.size)
    if (!r) return
    r.connected = true
    this.state.racers.set(r.userId, r)
    this.physicsRacers.push(makeRacer(r.userId))
    client.userData = { userId: r.userId }
  }

  private handleStart(client: Client): void {
    if (this.state.phase !== "lobby") return
    const opener = (client.userData as { userId?: string } | undefined)?.userId
    if (opener !== this.state.hostUserId) return
    if (this.state.racers.size < MIN_RACERS) return

    this.setPhase("countdown")
    this.clock.setTimeout(() => this.beginRunning(), COUNTDOWN_MS)
  }

  private handleMove(raw: unknown): void {
    const parsed = parseMove(raw)
    if (!parsed) return
    const physicsRacer = this.physicsRacers.find((r) => r.id === parsed.userId)
    if (!physicsRacer) return
    setMoving(physicsRacer, parsed.isMoving)
  }

  private handleSprintTap(raw: unknown): void {
    const userId = parseUserIdOnly(raw)
    if (!userId) return
    const physicsRacer = this.physicsRacers.find((r) => r.id === userId)
    if (!physicsRacer) return
    triggerSprintTap(physicsRacer, this.state.runningElapsedMs)
  }

  // ─── sim loop ────────────────────────────

  private beginRunning(): void {
    this.setPhase("running")
    this.state.runningElapsedMs = 0
    this.runningStartedAtMs = Date.now()
    this.simHandle = setInterval(() => this.simStep(), SIM_TICK_MS)
  }

  private simStep(): void {
    if (this.state.phase !== "running") return
    const nowMs = Date.now()
    const elapsed = nowMs - this.runningStartedAtMs
    this.state.runningElapsedMs = elapsed

    physicsTick(this.physicsRacers, SIM_TICK_MS, elapsed, this.state.distanceM)
    this.mirrorPhysicsToSchema()

    const allFinished = this.physicsRacers.every((r) => r.finished)
    const timedOut = elapsed >= RUNNING_TIMEOUT_MS
    if (allFinished || timedOut) this.finishRound(timedOut)
  }

  private finishRound(timeoutFired: boolean): void {
    this.stopSim()
    const placings = checkFinish(this.physicsRacers, timeoutFired)
    this.state.placings.clear()
    for (const p of placings) this.state.placings.push(placingToSchema(p))
    this.setPhase("finished")
  }

  /**
   * Central phase mutator — bumps `phaseStartMs` and notifies OrgRoom via
   * the registry so the garden's watch banner reflects lobby / countdown /
   * running / finished in real time instead of waiting for room disposal.
   */
  private setPhase(phase: "lobby" | "countdown" | "running" | "finished"): void {
    this.state.phase = phase
    this.state.phaseStartMs = Date.now()
    fireRacePhase(this.roomId, phase)
  }

  private mirrorPhysicsToSchema(): void {
    for (const r of this.physicsRacers) {
      const schema = this.state.racers.get(r.id)
      if (schema) copyRacerToSchema(r, schema)
    }
  }

  private stopSim(): void {
    if (this.simHandle) {
      clearInterval(this.simHandle)
      this.simHandle = null
    }
  }
}

function placingToSchema(p: Placing): PlacingState {
  const s = new PlacingState()
  s.racerId = p.racerId
  s.place = p.place
  s.finished = p.finished
  s.finishTimeMs = p.finishTimeMs
  s.distanceM = p.distanceM
  return s
}

interface MoveMsg { userId: string; isMoving: boolean }

function parseMove(raw: unknown): MoveMsg | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  if (typeof o.userId !== "string" || typeof o.isMoving !== "boolean") return null
  return { userId: o.userId, isMoving: o.isMoving }
}

function parseUserIdOnly(raw: unknown): string | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  return typeof o.userId === "string" ? o.userId : null
}

// Keep this export for RaceRoomState references in tests; avoids a test
// having to import both files.
export { RaceRoomState, RacerState }
