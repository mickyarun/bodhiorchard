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
import { getHouseDeskSeat, getHouseBedPosition, BREAK_SEATS } from "./WorldLayout"

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
}

/**
 * Compute placement for a single member based on their presence.
 *
 * `takenBreakSeats` is a mutable set of seat indices already assigned
 * in this placement pass — used to avoid double-booking break seats.
 */
export function computePlacement(
  input: MemberPlacementInput,
  takenBreakSeats: Set<number>,
): Placement {
  const { userId, presence, memberIndex, totalMembers } = input

  // ─── at_home → bed position in own house ───
  if (presence === "at_home") {
    const bed = getHouseBedPosition(memberIndex, totalMembers)
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
    const desk = getHouseDeskSeat(memberIndex, totalMembers)
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

  // ─── on_break → coffee bar or pool seat ───
  if (presence === "on_break") {
    for (let i = 0; i < BREAK_SEATS.length; i++) {
      if (takenBreakSeats.has(i)) continue
      const seat = BREAK_SEATS[i]
      takenBreakSeats.add(i)
      return {
        x: seat.x,
        y: seat.y,
        z: seat.z,
        yaw: seat.yaw,
        sitting: true,
        locationContext: `break_${seat.zone}`,
      }
    }
    return fallback(userId)
  }

  return fallback(userId)
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
