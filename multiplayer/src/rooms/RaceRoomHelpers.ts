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
import { RacerState } from "../schema/RacerState"

export interface RaceCreateOptions {
  orgId: string
  hostUserId: string
  hostName: string
  distanceM: number
  invitedUserIds: string[]
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
