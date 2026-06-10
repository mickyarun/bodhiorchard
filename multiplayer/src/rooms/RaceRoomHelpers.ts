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
 * RaceRoomHelpers — pure parsers + schema-adapters used by RaceRoom.
 *
 * Kept separate so `RaceRoom.ts` stays under the 300-line hard cap and
 * so the parsers can be unit-tested without spinning up Colyseus.
 */
import type { Racer } from "../../../shared/race/RacePhysics"
import type { Placing } from "../../../shared/race/types"
import { PlacingState } from "../schema/PlacingState"
import { RacerState } from "../schema/RacerState"
import type { RaceResultsPayload, RaceResultsPlacing } from "../bridge/BackendClient"

export interface RaceCreateOptions {
  orgId: string
  hostUserId: string
  hostName: string
  distanceM: number
  invitedUserIds: string[]
}

/** Race-identifying fields forwarded onto every results-POST payload. */
export interface RaceResultsHeader {
  roomId: string
  orgId: string
  hostUserId: string
  distanceM: number
}

/**
 * Parse + validate the options passed into `onCreate`.
 *
 * Colyseus forwards whatever the caller supplies to `matchMaker.createRoom`
 * — so the server must defend in depth against malformed or malicious
 * payloads even though the OrgRoom handler is the only intended caller.
 */
export function assertRaceCreateOptions(
  raw: unknown,
  allowedDistances: readonly number[],
): RaceCreateOptions {
  if (typeof raw !== "object" || raw === null) {
    throw new Error("RaceRoom.onCreate: options must be an object")
  }
  const o = raw as Record<string, unknown>

  const orgId = asString(o.orgId, "orgId")
  const hostUserId = asString(o.hostUserId, "hostUserId")
  const hostName = asString(o.hostName, "hostName")
  const distanceM = asNumber(o.distanceM, "distanceM")
  if (!allowedDistances.includes(distanceM)) {
    throw new Error(
      `RaceRoom.onCreate: distanceM=${distanceM} not in ${allowedDistances.join("/")}`,
    )
  }
  const invited = Array.isArray(o.invitedUserIds) ? o.invitedUserIds : []
  const invitedUserIds: string[] = []
  for (const v of invited) {
    if (typeof v === "string" && v.length > 0) invitedUserIds.push(v)
  }
  return { orgId, hostUserId, hostName, distanceM, invitedUserIds }
}

/**
 * Parse a `race_join` message payload and promote it to a freshly
 * initialised `RacerState`. Returns `null` on invalid payloads — RaceRoom
 * treats that as a no-op so a buggy client can't crash the room.
 */
export function buildRacerState(raw: unknown, laneIndex: number): RacerState | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  const userId = optionalString(o.userId)
  const name = optionalString(o.name)
  if (!userId || !name) return null
  const state = new RacerState()
  state.id = userId
  state.userId = userId
  state.name = name
  state.characterModel = optionalString(o.characterModel) ?? ""
  state.laneIndex = laneIndex
  return state
}

/**
 * Copy mutable physics fields onto the synced schema state. Invariant
 * fields (id, userId, name, characterModel, laneIndex, connected) are
 * never touched — they're set once at join time.
 */
export function copyRacerToSchema(phys: Racer, schema: RacerState): void {
  schema.positionM = phys.positionM
  schema.velocityMps = phys.velocityMps
  schema.finished = phys.finished
  schema.finishTimeMs = phys.finishTimeMs
  schema.isMoving = phys.isMoving
  schema.sprintUntilMs = phys.sprintUntilMs
  schema.staminaPct = phys.staminaPct
  schema.boostUntilMs = phys.boostUntilMs
  schema.jumpUntilMs = phys.jumpUntilMs
  schema.knockdownUntilMs = phys.knockdownUntilMs
}

function asString(v: unknown, name: string): string {
  if (typeof v !== "string" || v.length === 0) {
    throw new Error(`RaceRoom.onCreate: ${name} must be a non-empty string`)
  }
  return v
}

function asNumber(v: unknown, name: string): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(`RaceRoom.onCreate: ${name} must be a finite number`)
  }
  return v
}

function optionalString(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null
}

/**
 * Promote a pure-physics `Placing` to its Colyseus-synced schema mirror.
 *
 * Schema construction lives here (not in RaceRoom) so RaceRoom keeps its
 * orchestration role and the field-by-field mapping is unit-testable.
 */
export function placingToSchema(p: Placing): PlacingState {
  const s = new PlacingState()
  s.racerId = p.racerId
  s.place = p.place
  s.finished = p.finished
  s.finishTimeMs = p.finishTimeMs
  s.distanceM = p.distanceM
  return s
}

/**
 * Build the JSON payload posted to the backend on race dispose.
 *
 * Returns `null` when there's nothing meaningful to persist:
 *   - empty placings (room disposed before `finishRound` ever ran)
 *   - placings with zero finishers (room disposed mid-race with everyone DNF)
 *
 * Extracted from `RaceRoom.onDispose` so the multi-finisher contract is
 * lockable in vitest — the test suite proves that **every** placing
 * passed in surfaces in the outgoing payload, finishers and DNFs alike.
 * A regression here is what would produce the "only winner appears on
 * the leaderboard" symptom, so the test is the canary.
 */
export function buildRaceResultsPayload(
  header: RaceResultsHeader,
  placings: Iterable<PlacingState>,
): RaceResultsPayload | null {
  const rows: RaceResultsPlacing[] = []
  let anyFinisher = false
  for (const p of placings) {
    rows.push({
      userId: p.racerId,
      finishTimeMs: p.finished ? p.finishTimeMs : null,
      place: p.place,
      finished: p.finished,
      distanceMReached: p.distanceM,
      distanceM: header.distanceM,
    })
    if (p.finished) anyFinisher = true
  }
  if (rows.length === 0 || !anyFinisher) return null
  return {
    roomId: header.roomId,
    orgId: header.orgId,
    hostUserId: header.hostUserId,
    distanceM: header.distanceM,
    placings: rows,
  }
}
