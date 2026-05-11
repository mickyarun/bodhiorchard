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
 * MemberPlacement — pure function to compute initial position for a member.
 *
 * Mirror of frontend `CharacterSystem.getPlacement()` logic.
 * Given a member and their presence state, returns (x, y, z, yaw, sitting).
 *
 *   'active'      → seated at their house desk
 *   'at_home'     → standing at their house bed
 *   'on_break'    → seated at pool or coffee bar
 */
import { getHouseDeskSeat, getHouseBedPosition } from "./WorldLayout"
import type { BreakSeat } from "./BreakSeatGenerator"

export type PresenceState = "active" | "on_break" | "at_home"

export interface Placement {
  x: number
  y: number
  z: number
  yaw: number
  sitting: boolean
  locationContext: string  // "garden" | "house_{memberId}" | "break_{zone}"
}

export interface MemberPlacementInput {
  userId: string
  presence: PresenceState
  memberIndex: number
  totalMembers: number
  houseLevel?: number
}

/**
 * Compute placement for a single member based on their presence.
 *
 * `takenBreakSeats` is a mutable set of seat indices already assigned
 * in this placement pass — used to avoid double-booking break seats.
 *
 * `preferredZone` is an optional hint for `on_break` placement. When set,
 * the break-seat loop first tries seats in that zone (e.g. "cafeteria",
 * "pool_resort", "coffee_bar"); if all are taken or the zone doesn't exist,
 * it falls back to the global first-available order. Snapshot-load callers
 * pass no preferred zone (the round-robin order in `breakSeats` wins).
 * Live callers (inferred presence for non-Slack users) pass the zone they
 * want so e.g. "idle for 10 minutes" → cafeteria, not coffee bar.
 */
export function computePlacement(
  input: MemberPlacementInput,
  takenBreakSeats: Set<number>,
  breakSeats: readonly BreakSeat[],
  preferredZone?: string,
): Placement {
  const { userId, presence, memberIndex, totalMembers, houseLevel } = input

  // ─── at_home → bed position in own house ───
  if (presence === "at_home") {
    const bed = getHouseBedPosition(memberIndex, totalMembers, houseLevel)
    if (bed) {
      return {
        x: bed.x,
        y: bed.y,
        z: bed.z,
        yaw: bed.yaw,
        sitting: false,
        locationContext: `house_${userId}`,
      }
    }
    return fallback(userId)
  }

  // ─── active → desk seat in own house ───
  if (presence === "active") {
    const desk = getHouseDeskSeat(memberIndex, totalMembers, houseLevel)
    if (desk) {
      return {
        x: desk.x,
        y: desk.y,
        z: desk.z,
        yaw: desk.yaw,
        sitting: true,
        locationContext: `house_${userId}`,
      }
    }
    return fallback(userId)
  }

  // ─── on_break → break zone seat ───
  if (presence === "on_break") {
    // Pass 1: prefer seats in the requested zone (if any). Skips seats that
    // are already taken so two members with the same preferredZone fan out
    // across the zone's available seats before spilling to other zones.
    if (preferredZone) {
      const preferred = findBreakSeat(breakSeats, takenBreakSeats, preferredZone)
      if (preferred) return preferred
    }
    // Pass 2: any available seat in any zone (original behavior).
    const anySeat = findBreakSeat(breakSeats, takenBreakSeats)
    if (anySeat) return anySeat
    return fallback(userId)
  }

  return fallback(userId)
}

/**
 * Find the first unoccupied `breakSeats` entry, optionally filtered by zone.
 * Mutates `takenBreakSeats` on success — the found index is marked taken.
 * Returns `null` if no seat matches.
 *
 * `locationContext` is formatted as `break_{zone}_{seatIndex}` so callers can
 * reconstruct the exact taken seat from the string. A plain `break_{zone}`
 * would lose information when there are multiple seats per zone (as there are
 * for coffee_bar, pool_resort, and cafeteria). Parsing reference in
 * `OrgRoom.computeHomePlacement`.
 */
function findBreakSeat(
  breakSeats: readonly BreakSeat[],
  takenBreakSeats: Set<number>,
  zoneFilter?: string,
): Placement | null {
  for (let i = 0; i < breakSeats.length; i++) {
    if (takenBreakSeats.has(i)) continue
    const seat = breakSeats[i]
    if (zoneFilter && seat.zone !== zoneFilter) continue
    takenBreakSeats.add(i)
    return {
      x: seat.x,
      y: seat.y,
      z: seat.z,
      yaw: seat.yaw,
      sitting: true,
      locationContext: `break_${seat.zone}_${i}`,
    }
  }
  return null
}

function fallback(userId: string): Placement {
  return {
    x: 0,
    y: 0,
    z: 0,
    yaw: 0,
    sitting: false,
    locationContext: `garden`,
  }
}
