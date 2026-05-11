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
 * RaceRoomClient — one Colyseus race-room connection per component.
 *
 * Unlike `OrgRoomClient` (singleton; one org room per session), race
 * rooms are short-lived — one per race instance — and a user may be in
 * zero or one at a time. So this class is instantiated directly by
 * `RaceRoomView.vue` and destroyed on unmount.
 *
 * Join flow:
 *   1. Construct with a server URL.
 *   2. `joinById(roomId, auth)` — joins the pre-existing room the host
 *      created via OrgRoom's `race_create` handler.
 *   3. Reactive callbacks fire as server state updates.
 *   4. Send helpers turn user input into server messages.
 *   5. `destroy()` leaves the room cleanly.
 *
 * Reactive surface is a single `onStateChange` callback that receives a
 * plain snapshot object — the consumer maps it to Vue refs / the engine.
 */
import { Client, getStateCallbacks, Room } from "@colyseus/sdk"
import type { RacePhase, Placing } from "@shared/race/types"
import { resolveColyseusUrl } from "./colyseusUrl"

export interface RacerSnapshot {
  id: string
  userId: string
  name: string
  characterModel: string
  laneIndex: number
  positionM: number
  velocityMps: number
  finished: boolean
  finishTimeMs: number
  isMoving: boolean
  sprintUntilMs: number
  connected: boolean
}

export interface RaceStateSnapshot {
  orgId: string
  hostUserId: string
  hostName: string
  distanceM: number
  phase: RacePhase
  phaseStartMs: number
  runningElapsedMs: number
  invitedUserIds: string[]
  racers: RacerSnapshot[]
  placings: Placing[]
}

interface RawRacer {
  id?: string
  userId?: string
  name?: string
  characterModel?: string
  laneIndex?: number
  positionM?: number
  velocityMps?: number
  finished?: boolean
  finishTimeMs?: number
  isMoving?: boolean
  sprintUntilMs?: number
  connected?: boolean
}

interface RawPlacing {
  racerId?: string
  place?: number
  finished?: boolean
  finishTimeMs?: number
  distanceM?: number
}

/** Minimal ArraySchema shape — just the iteration primitive we use to
 *  rebuild our plain-array snapshot. */
interface ArrayLike<T> {
  forEach: (fn: (v: T) => void) => void
}

interface RaceStateShape {
  orgId: string
  hostUserId: string
  hostName: string
  distanceM: number
  phase: RacePhase
  phaseStartMs: number
  runningElapsedMs: number
  // Collections are populated by the first state patch but can be
  // undefined during the brief window between `joinById` resolving and
  // the first schema sync — guarded in `snapshotFromState`.
  invitedUserIds: ArrayLike<string>
  racers: Map<string, RawRacer>
  placings: ArrayLike<RawPlacing>
}

export interface RaceAuth {
  userId: string
  name: string
  characterModel?: string
  token?: string
}

/**
 * Public-only view of `RaceRoomClient`. Exposing just the methods + read
 * accessors lets Vue components type their props without fighting the
 * private-fields stripping that happens when a class instance is held in
 * a Vue `ref`.
 */
export interface RaceRoomClientLike {
  readonly isHost: boolean
  readonly roomId: string | undefined
  onStateChange: ((snapshot: RaceStateSnapshot) => void) | null
  sendRaceJoin(): void
  sendRaceStart(): void
  sendMove(isMoving: boolean): void
  sendSprintTap(): void
}

export class RaceRoomClient {
  private client: Client
  private room: Room | null = null
  /** Local mirror — updated on every state delta and passed to onStateChange. */
  private snapshot: RaceStateSnapshot = emptySnapshot()
  /** Set once at join time so `isHost` works without inspecting every delta. */
  private userId = ""

  /** Fires with the latest snapshot on every server state change. */
  onStateChange: ((snapshot: RaceStateSnapshot) => void) | null = null

  /** Auth fields carried into `race_join` after `joinById` resolves. */
  private authName = ""
  private authCharacterModel = ""

  constructor(serverUrl?: string) {
    this.client = new Client(serverUrl ?? resolveColyseusUrl())
  }

  get isHost(): boolean {
    return this.userId === this.snapshot.hostUserId && this.userId !== ""
  }

  get roomId(): string | undefined {
    return this.room?.roomId
  }

  async joinById(roomId: string, auth: RaceAuth): Promise<void> {
    if (this.room) await this.leave()
    this.userId = auth.userId
    this.authName = auth.name
    this.authCharacterModel = auth.characterModel ?? ""
    this.room = await this.client.joinById(roomId, {
      userId: auth.userId,
      name: auth.name,
      characterModel: this.authCharacterModel,
      token: auth.token ?? "",
    })
    this.wireState()
    // Tell the server we want a racer slot (host auto-joins their own room).
    this.sendRaceJoin()
  }

  async leave(): Promise<void> {
    if (!this.room) return
    try {
      await this.room.leave()
    } catch {
      // Already disconnected — nothing to recover.
    }
    this.room = null
    this.snapshot = emptySnapshot()
  }

  sendRaceJoin(): void {
    this.room?.send("race_join", {
      userId: this.userId,
      name: this.authName || this.userId,
      characterModel: this.authCharacterModel,
    })
  }

  sendRaceStart(): void {
    // UX guard only — server re-checks that the sender is the host.
    if (!this.isHost) return
    this.room?.send("race_start", {})
  }

  sendMove(isMoving: boolean): void {
    this.room?.send("race_move", { userId: this.userId, isMoving })
  }

  sendSprintTap(): void {
    this.room?.send("race_sprint_tap", { userId: this.userId })
  }

  destroy(): void {
    void this.leave()
    this.onStateChange = null
  }

  private wireState(): void {
    if (!this.room) return
    const room = this.room as Room<RaceStateShape>
    const $ = getStateCallbacks(room)
    const state = $(room.state)

    const publish = (): void => {
      try {
        this.snapshot = snapshotFromState(room.state)
        this.onStateChange?.(this.snapshot)
      } catch (err) {
        // Never let a snapshot read crash the join promise — the next
        // onChange delta will publish a fresh snapshot and recover.
        console.warn("[RaceRoomClient] snapshot read skipped:", err)
      }
    }

    $(room.state).onChange(() => publish())

    state.racers.onAdd((r: RawRacer) => {
      publish()
      $(r).onChange(() => publish())
    }, true)
    state.racers.onRemove(() => publish())

    // ArraySchema: the state-level `.onChange` above fires on every mutation
    // of any schema field, including arrays, so we don't need a dedicated
    // listener — `publish` will rebuild placings from the current array.

    publish()
  }
}

function snapshotFromState(s: RaceStateShape): RaceStateSnapshot {
  // Schema fields are ArraySchema/MapSchema once populated, but may be
  // undefined on the very first `publish()` call if Colyseus hasn't yet
  // hydrated the collections. Defensive guards keep the first render
  // deterministic instead of throwing into the caller's async chain.
  const racers: RacerSnapshot[] = []
  s.racers?.forEach((r) => racers.push(racerSnapshot(r)))

  const placings: Placing[] = []
  s.placings?.forEach((p: RawPlacing) =>
    placings.push({
      racerId: p.racerId ?? "",
      place: p.place ?? 0,
      finished: p.finished ?? false,
      finishTimeMs: p.finishTimeMs ?? 0,
      distanceM: p.distanceM ?? 0,
    }),
  )

  const invited: string[] = []
  s.invitedUserIds?.forEach((id: string) => invited.push(id))

  return {
    orgId: s.orgId ?? "",
    hostUserId: s.hostUserId ?? "",
    hostName: s.hostName ?? "",
    distanceM: s.distanceM ?? 0,
    phase: (s.phase as RacePhase) ?? "lobby",
    phaseStartMs: s.phaseStartMs ?? 0,
    runningElapsedMs: s.runningElapsedMs ?? 0,
    invitedUserIds: invited,
    racers,
    placings,
  }
}

function racerSnapshot(r: RawRacer): RacerSnapshot {
  return {
    id: r.id ?? "",
    userId: r.userId ?? "",
    name: r.name ?? "",
    characterModel: r.characterModel ?? "",
    laneIndex: r.laneIndex ?? 0,
    positionM: r.positionM ?? 0,
    velocityMps: r.velocityMps ?? 0,
    finished: r.finished ?? false,
    finishTimeMs: r.finishTimeMs ?? 0,
    isMoving: r.isMoving ?? false,
    sprintUntilMs: r.sprintUntilMs ?? 0,
    connected: r.connected ?? false,
  }
}

function emptySnapshot(): RaceStateSnapshot {
  return {
    orgId: "",
    hostUserId: "",
    hostName: "",
    distanceM: 0,
    phase: "lobby",
    phaseStartMs: 0,
    runningElapsedMs: 0,
    invitedUserIds: [],
    racers: [],
    placings: [],
  }
}
