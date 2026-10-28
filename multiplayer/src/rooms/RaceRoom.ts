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
 * Size budget: room orchestration only — parsing, validation, and schema
 * adapters live in `RaceRoomHelpers.ts`, bot driving in `RaceBotDriver.ts`.
 * The lobby/invite flows have pushed it past its original 300-line cap;
 * extracting them into a lobby handler is the tracked follow-up refactor.
 */
import { Room, Client, type RoomException, type RoomMethodName } from "colyseus"
import { reportRoomException } from "./roomExceptions"
import type { Delayed } from "colyseus"
import {
  CANCEL_FLUSH_GRACE_MS,
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
import { triggerJump } from "../../../shared/race/RaceTrackFeatures"
import { RaceRoomState } from "../schema/RaceRoomState"
import { RacerState } from "../schema/RacerState"
import {
  assertRaceCreateOptions,
  buildBotRacerState,
  buildRacerState,
  buildRaceResultsPayload,
  copyRacerToSchema,
  parseAddInviteesPayload,
  parseMove,
  parseUserIdOnly,
  placingToSchema,
  type RaceCreateOptions,
} from "./RaceRoomHelpers"
import { driveBots } from "./RaceBotDriver"
import { raceIdentityFrom, raceIdentityOf, type RaceJoinOptions } from "./RaceRoomAuth"
import { postRaceInvite, postRaceResults } from "../bridge/BackendClient"
import { fireRaceDispose, fireRacePhase } from "../bridge/RaceRegistry"
import { consumeRaceCreateTicket } from "../bridge/RaceCreateTickets"
import { verifyJoin, type JoinIdentity } from "../auth/verifyJoin"

const SIM_TICK_MS = TICK_MS

export class RaceRoom extends Room<{ state: RaceRoomState }> {
  maxClients = MAX_RACERS * 2 // racers + spectators

  /** In-memory physics mirror — schema state is updated from this each tick. */
  private physicsRacers: Racer[] = []
  /** Subset of physicsRacers driven by RaceBotDriver (dev mode only). */
  private botRacers: Racer[] = []
  private simHandle: Delayed | null = null
  /** Wall-clock at which running phase began (used to compute elapsedMs). */
  private runningStartedAtMs = 0

  onCreate(rawOptions: unknown): void {
    // Only OrgRaceHandler, for a verified host, opens races (see RaceCreateTickets).
    const ticket = (rawOptions as { createTicket?: unknown } | null)?.createTicket
    if (!consumeRaceCreateTicket(ticket)) throw new Error("race rooms are created by the server")
    const options = assertRaceCreateOptions(rawOptions, ALLOWED_DISTANCES_M)
    this.seedState(options)
    this.seedBots(options.botCount)
    this.registerHandlers()
    // Keep the lobby alive even when zero clients are connected so the
    // host can switch tabs (or close the page) while waiting for an
    // invitee to come online and click their notification. A hard cap
    // below prevents abandoned lobbies from accumulating. autoDispose is
    // restored in `beginRunning` so finished rooms clean up normally.
    this.autoDispose = false
    this.clock.setTimeout(() => this.expireLobbyIfStillWaiting(), LOBBY_MAX_MS)
  }

  /** Verify the join token for this race's org; its user becomes the racer identity. */
  async onAuth(_client: Client, options: RaceJoinOptions): Promise<JoinIdentity> {
    return verifyJoin(options, this.state.orgId)
  }

  onJoin(client: Client, options: RaceJoinOptions, auth?: JoinIdentity): void {
    // `options` are the raw client join options; `auth` is what onAuth
    // returned. Racing, host actions and inputs all key off this identity.
    const identity = raceIdentityFrom(auth, options)
    // Invites quote the host's name, so it is the verified one, not the
    // name the room was created with.
    if (identity.userId === this.state.hostUserId) this.state.hostName = identity.name
    client.userData = identity
    console.log(
      `[RaceRoom ${this.roomId}] ${identity?.name ?? "anonymous"} (${client.sessionId}) joined`,
    )
  }

  onLeave(client: Client): void {
    // The leaver keeps their slot but gets `connected=false` so the client
    // HUD can show ghost status. Only their own racer is touched, and only
    // when no other open session (a second tab) is still joined as them.
    const userId = racerUserId(client)
    if (!userId) return
    const stillJoined = this.clients.some(
      (c) => c.sessionId !== client.sessionId && racerUserId(c) === userId,
    )
    const racer = this.state.racers.get(userId)
    if (racer && !stillJoined) racer.connected = false
  }

  /** Report a throwing handler or timer instead of letting it exit the process. */
  onUncaughtException(error: RoomException, methodName: RoomMethodName): void {
    reportRoomException(this, error, methodName)
    // The sim tick is the only interval: one that threw will throw on every
    // tick, so end the race instead of logging the same failure at 20Hz.
    if (methodName === "setInterval") this.abandonBrokenRace()
  }

  private abandonBrokenRace(): void {
    this.stopSim()
    this.setPhase("finished")
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
    state.trackShape = opts.trackShape
    state.phase = "lobby"
    state.phaseStartMs = Date.now()
    for (const id of opts.invitedUserIds) state.invitedUserIds.push(id)
    this.setState(state)
  }

  /**
   * Seed dev-mode bot racers (count already production-gated to 0 by
   * resolveBotCount). Bots occupy the first lanes and arrive connected,
   * so they count toward MIN_RACERS — host + one bot can start. Driven
   * each tick by RaceBotDriver; excluded from the results POST.
   */
  private seedBots(botCount: number): void {
    for (let n = 1; n <= botCount; n++) {
      const bot = buildBotRacerState(n, this.state.racers.size)
      this.state.racers.set(bot.userId, bot)
      const phys = makeRacer(bot.userId)
      this.physicsRacers.push(phys)
      this.botRacers.push(phys)
    }
    if (botCount > 0) {
      console.log(`[RaceRoom ${this.roomId}] seeded ${botCount} test bot(s) (dev mode)`)
    }
  }

  private registerHandlers(): void {
    this.onMessage("race_join", (client) => this.handleJoin(client))
    this.onMessage("race_start", (client) => this.handleStart(client))
    this.onMessage("race_cancel", (client) => this.handleCancel(client))
    this.onMessage("race_add_invitees", (client, data: unknown) =>
      this.handleAddInvitees(client, data),
    )
    this.onMessage("race_move", (client, data: unknown) => this.handleMove(client, data))
    this.onMessage("race_sprint_tap", (client, data: unknown) =>
      this.handleSprintTap(client, data),
    )
    this.onMessage("race_jump", (client, data: unknown) => this.handleJump(client, data))
  }

  // ─── message handlers ────────────────────

  /**
   * Seat the client as a racer. The racer is always the identity the client
   * joined with; the race_join payload is not consulted, so one naming
   * another user changes nothing.
   */
  private handleJoin(client: Client): void {
    const identity = raceIdentityOf(client)
    if (!identity) return
    // Same user again (second tab, page refresh, in any phase): re-bind to
    // the existing racer. A second physics entry would duplicate their
    // placing and the results POST would carry two rows for one user.
    const existing = this.state.racers.get(identity.userId)
    if (existing) {
      existing.connected = true
      return
    }
    if (this.state.phase !== "lobby") return
    if (!this.mayRace(identity.userId)) return
    if (this.state.racers.size >= MAX_RACERS) return
    const r = buildRacerState(identity, this.state.racers.size)
    if (!r) return
    r.connected = true
    this.state.racers.set(r.userId, r)
    this.physicsRacers.push(makeRacer(r.userId))
  }

  /** Only the host and the users they invited take a lane; anyone else watches. */
  private mayRace(userId: string): boolean {
    return userId === this.state.hostUserId || this.state.invitedUserIds.includes(userId)
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
    // Defer the disconnect by one patch cycle so the `race_cancelled`
    // broadcast above actually flushes to clients first. Disconnecting in
    // the same tick closes the sockets before Colyseus sends the frame, so
    // the host's `onRaceCancelled` handler — which drives the toast and the
    // navigation back to the garden — would never fire.
    this.clock.setTimeout(() => this.disconnect(), CANCEL_FLUSH_GRACE_MS)
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

  private handleMove(client: Client, raw: unknown): void {
    const parsed = parseMove(raw)
    if (!parsed || parsed.userId !== racerUserId(client)) return
    const physicsRacer = this.physicsRacers.find((r) => r.id === parsed.userId)
    if (!physicsRacer) return
    setMoving(physicsRacer, parsed.isMoving)
  }

  private handleSprintTap(client: Client, raw: unknown): void {
    const userId = parseUserIdOnly(raw)
    if (!userId || userId !== racerUserId(client)) return
    const physicsRacer = this.physicsRacers.find((r) => r.id === userId)
    if (!physicsRacer) return
    triggerSprintTap(physicsRacer, this.state.runningElapsedMs)
  }

  private handleJump(client: Client, raw: unknown): void {
    const userId = parseUserIdOnly(raw)
    if (!userId || userId !== racerUserId(client)) return
    const physicsRacer = this.physicsRacers.find((r) => r.id === userId)
    if (!physicsRacer) return
    triggerJump(physicsRacer, this.state.runningElapsedMs)
  }

  // ─── sim loop ────────────────────────────

  private beginRunning(): void {
    this.setPhase("running")
    this.state.runningElapsedMs = 0
    this.runningStartedAtMs = Date.now()
    // Room clock: guarded by onUncaughtException and cleared on dispose.
    this.simHandle = this.clock.setInterval(() => this.simStep(), SIM_TICK_MS)
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

    // Bots synthesise their inputs through the same shared entry points
    // human messages use — must run before the physics integration so a
    // bot's tap lands on the same tick a human's message would.
    driveBots(this.botRacers, elapsed, SIM_TICK_MS, this.state.distanceM)
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
      this.simHandle.clear()
      this.simHandle = null
    }
  }
}

/**
 * The user a client joined the room as, or null if it has no identity.
 * Inputs naming any other racer are dropped: a client drives only itself.
 */
function racerUserId(client: Client): string | null {
  return raceIdentityOf(client)?.userId ?? null
}

// Keep this export for RaceRoomState references in tests; avoids a test
// having to import both files.
export { RaceRoomState, RacerState }
