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
  LOBBY_MAX_MS,
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
import { RaceRoomState } from "../schema/RaceRoomState"
import { RacerState } from "../schema/RacerState"
import {
  assertRaceCreateOptions,
  buildRacerState,
  buildRaceResultsPayload,
  copyRacerToSchema,
  placingToSchema,
  type RaceCreateOptions,
} from "./RaceRoomHelpers"
import { postRaceInvite, postRaceResults } from "../bridge/BackendClient"
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
    // Keep the lobby alive even when zero clients are connected so the
    // host can switch tabs (or close the page) while waiting for an
    // invitee to come online and click their notification. A hard cap
    // below prevents abandoned lobbies from accumulating. autoDispose is
    // restored in `beginRunning` so finished rooms clean up normally.
    this.autoDispose = false
    this.clock.setTimeout(() => this.expireLobbyIfStillWaiting(), LOBBY_MAX_MS)
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

    const payload = buildRaceResultsPayload(
      {
        roomId: this.roomId,
        orgId: this.state.orgId,
        hostUserId: this.state.hostUserId,
        distanceM: this.state.distanceM,
      },
      this.state.placings,
    )
    if (!payload) {
      const placingCount = this.state.placings.length
      const dnfCount = Array.from(this.state.placings).filter((p) => !p.finished).length
      console.log(
        `[RaceRoom ${this.roomId}] disposed without postable results — ` +
          `placings=${placingCount} finishers=0 dnfs=${dnfCount}`,
      )
      return
    }

    // Surfaces the count being POSTed so the "only winner reaches the
    // leaderboard" symptom is visible in logs without needing a DB dump.
    const finisherCount = payload.placings.filter((p) => p.finished).length
    console.log(
      `[RaceRoom ${this.roomId}] posting race results: placings=${payload.placings.length} ` +
        `finishers=${finisherCount} distanceM=${payload.distanceM}`,
    )

    // Fire-and-forget — Colyseus cannot await dispose. Network failures here
    // do NOT roll back local state; the bridge is expected to retry on 5xx.
    postRaceResults(payload).catch((err: unknown) => {
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
    this.onMessage("race_cancel", (client) => this.handleCancel(client))
    this.onMessage("race_add_invitees", (client, data: unknown) =>
      this.handleAddInvitees(client, data),
    )
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

  /**
   * Host-initiated lobby cancel. Tells everyone still in the room their
   * race was cancelled (via a broadcast they can render as a toast), then
   * disconnects all clients so the room disposes. Only honoured before
   * `running` — once the sim is live, abandoning a race must keep the
   * `finished` flow intact so existing finishers still get their stats.
   */
  private handleCancel(client: Client): void {
    if (this.state.phase !== "lobby" && this.state.phase !== "countdown") return
    const opener = (client.userData as { userId?: string } | undefined)?.userId
    if (opener !== this.state.hostUserId) return
    console.log(
      `[RaceRoom ${this.roomId}] host ${this.state.hostName} cancelled the race in ${this.state.phase} phase`,
    )
    this.broadcast("race_cancelled", { hostName: this.state.hostName })
    // Allow normal autoDispose to clean up — disconnect terminates every
    // client, the room sees `clients=0`, and the timeout we set in
    // onCreate (or the 15s default after start) takes care of disposal.
    this.autoDispose = true
    this.disconnect()
  }

  /**
   * Host-initiated "invite more" from the lobby. Adds new user ids to
   * `state.invitedUserIds` and fires a notification per new invitee via
   * the backend bridge — same path as `OrgRaceHandler` uses for the
   * initial create, so the recipient flow (toast + bell + decline) is
   * identical. Caps total participants at MAX_RACERS.
   */
  private handleAddInvitees(client: Client, raw: unknown): void {
    if (this.state.phase !== "lobby") return
    const opener = (client.userData as { userId?: string } | undefined)?.userId
    if (opener !== this.state.hostUserId) return

    const ids = parseAddInviteesPayload(raw)
    if (ids.length === 0) return

    const known = new Set<string>(this.state.invitedUserIds)
    this.state.racers.forEach((_r, key) => known.add(key))

    // Cap at MAX_RACERS counting host + invitees + already-joined racers.
    // Slot budget is whatever's left below MAX_RACERS.
    const inUse = known.size
    const slotsLeft = Math.max(0, MAX_RACERS - inUse)
    const additions: string[] = []
    for (const id of ids) {
      if (additions.length >= slotsLeft) break
      if (known.has(id)) continue
      known.add(id)
      additions.push(id)
    }
    if (additions.length === 0) return

    for (const id of additions) this.state.invitedUserIds.push(id)

    // Fire the per-recipient invite POSTs in parallel. Failure of any
    // individual post is logged by BackendClient and doesn't roll back
    // the local state change — a recipient who missed the notification
    // will only see it next time they refresh the bell, which is the
    // same failure mode as the create-time invite.
    void Promise.all(
      additions.map((recipientUserId) =>
        postRaceInvite({
          orgId: this.state.orgId,
          recipientUserId,
          hostUserId: this.state.hostUserId,
          hostName: this.state.hostName,
          roomId: this.roomId,
          distanceM: this.state.distanceM,
        }),
      ),
    )

    console.log(
      `[RaceRoom ${this.roomId}] +${additions.length} invitees: ${additions.join(", ")}`,
    )
  }

  private handleStart(client: Client): void {
    if (this.state.phase !== "lobby") return
    const opener = (client.userData as { userId?: string } | undefined)?.userId
    if (opener !== this.state.hostUserId) return
    if (this.state.racers.size < MIN_RACERS) return

    // Host commitment moment: once the countdown starts, abandonment by
    // every client should let the room dispose normally rather than
    // tying the multiplayer process up running a zombie sim for
    // RUNNING_TIMEOUT_MS. autoDispose=false was only there to protect
    // the lobby waiting on offline invitees.
    this.autoDispose = true
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

  /**
   * Backend-initiated removal of a declined invitee. Drops the user id
   * from the invited list so Alice's lobby stops showing them as
   * "Hasn't joined yet". Also drops them from the joined-racers map +
   * physics array defensively in case the decline raced with a join
   * (unusual but possible if the user had two tabs open). No-op once
   * the race has left the lobby — past that point the slot is real
   * (or already DNF) and we don't rewrite the racer list mid-sim.
   */
  removeInvitee(userId: string): void {
    if (this.state.phase !== "lobby") return

    // ArraySchema has no remove-by-value primitive; rebuild without the
    // declined id. Filter then push back to preserve schema semantics.
    const remaining: string[] = []
    this.state.invitedUserIds.forEach((id) => {
      if (id !== userId) remaining.push(id)
    })
    if (remaining.length === this.state.invitedUserIds.length) return
    this.state.invitedUserIds.clear()
    for (const id of remaining) this.state.invitedUserIds.push(id)

    // Defensive: if the user had somehow already joined the race room
    // before declining (two tabs, race condition), drop their racer
    // slot too. Otherwise Alice's lobby would still show them locked in.
    if (this.state.racers.has(userId)) {
      this.state.racers.delete(userId)
      this.physicsRacers = this.physicsRacers.filter((r) => r.id !== userId)
    }

    console.log(
      `[RaceRoom ${this.roomId}] invitee declined ${userId} — ` +
        `invitedUserIds=${this.state.invitedUserIds.length} ` +
        `racers=${this.state.racers.size}`,
    )
  }

  /**
   * Hard cap on lobby lifetime — disposes the room when LOBBY_MAX_MS
   * elapses since creation IF the race never advanced past lobby. If
   * someone hit Start in the meantime, the phase will already be
   * `countdown`/`running`/`finished` and we leave the in-flight race
   * alone (its own simStep + autoDispose handle cleanup).
   */
  private expireLobbyIfStillWaiting(): void {
    if (this.state.phase !== "lobby") return
    console.log(
      `[RaceRoom ${this.roomId}] lobby expired after ${LOBBY_MAX_MS}ms — disposing`,
    )
    // Mirror `handleCancel`: `disconnect()` boots every client, but the
    // room only auto-disposes when `autoDispose === true`. Without this
    // flip the room lingers until the process restarts.
    this.autoDispose = true
    this.disconnect()
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
    if (allFinished || timedOut) void this.finishRound(timedOut)
  }

  private async finishRound(timeoutFired: boolean): Promise<void> {
    this.stopSim()
    const placings = checkFinish(this.physicsRacers, timeoutFired)
    this.state.placings.clear()
    for (const p of placings) this.state.placings.push(placingToSchema(p))

    // Persist the result rows BEFORE flipping the phase, so the client's
    // end-of-race leaderboard fetch (which fires the moment phase becomes
    // "finished") sees the just-completed times. Posting on `onDispose`
    // alone left a ~10–60 s window — long enough that the user reliably
    // saw "old" leaderboard data sitting next to their fresh race result.
    // Idempotent on (room_id, user_id), so the dispose-side post still
    // works as a safety net if this one is interrupted.
    const payload = buildRaceResultsPayload(
      {
        roomId: this.roomId,
        orgId: this.state.orgId,
        hostUserId: this.state.hostUserId,
        distanceM: this.state.distanceM,
      },
      this.state.placings,
    )
    if (payload) {
      try {
        await postRaceResults(payload)
      } catch (err) {
        console.error(`[RaceRoom ${this.roomId}] postRaceResults failed:`, err)
      }
    }

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

/**
 * Parse a `race_add_invitees` payload into a clean string array.
 * Drops empty / non-string entries silently so a buggy client can't
 * push junk into `state.invitedUserIds`.
 */
function parseAddInviteesPayload(raw: unknown): string[] {
  if (typeof raw !== "object" || raw === null) return []
  const o = raw as Record<string, unknown>
  const arr = o.userIds
  if (!Array.isArray(arr)) return []
  const out: string[] = []
  for (const v of arr) {
    if (typeof v === "string" && v.length > 0) out.push(v)
  }
  return out
}

// Keep this export for RaceRoomState references in tests; avoids a test
// having to import both files.
export { RaceRoomState, RacerState }
