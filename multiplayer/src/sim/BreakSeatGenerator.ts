// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * BreakSeatGenerator — programmatic break-zone seat computation.
 *
 * Generates seat positions for cafeteria, coffee bar, and pool zones.
 * Cafeteria + coffee bar layouts come from `shared/world/breakSeats.ts`,
 * the same module the frontend builders import — so server-placed
 * characters sit on exactly the chairs the client renders.
 *
 * Scaling: targets ~60% of team size across all break zones so multiple
 * members can take breaks simultaneously without overlapping. The pool
 * is capped at 6 (physical umbrella sets); cafeteria and coffee bar
 * expose only as many seats as the frontend draws (count clamped to
 * breakSeatCount(layout)).
 *
 * Zone positions are read from the shared `getZones()` accessor — the
 * same source of truth as the frontend's WorldLayout.
 */

import { requireZone } from "./WorldLayout"
import {
  CAFETERIA_LAYOUT,
  COFFEE_BAR_LAYOUT,
  breakSeatCount,
  forEachBreakSeat,
  type BreakZoneLayout,
} from "../../../shared/world/breakSeats"

// ─── Seat type ──────────────────────────────────────────────────────────────

export interface BreakSeat {
  zone: string
  x: number
  y: number
  z: number
  yaw: number
}

// ─── Distribution ratio ─────────────────────────────────────────────────────

/** Target: 60% of team can sit at break zones simultaneously. */
const BREAK_RATIO = 0.6

/** Max pool seats (limited by physical umbrella GLB sets). */
const POOL_MAX = 6

/**
 * Minimum seats per zone — matches the physical furniture count built by
 * each frontend builder. Cafeteria + coffee bar derive from the shared
 * layout so the two sides can never drift again. Pool stays hardcoded;
 * its umbrella set count is owned by PoolResortBuilder.
 */
const CAFE_MIN = breakSeatCount(CAFETERIA_LAYOUT)  // 4 tables × 2 benches = 8
const COFFEE_MIN = breakSeatCount(COFFEE_BAR_LAYOUT) // 4 tables × 2 chairs = 8
const POOL_MIN = 6     // PoolResortBuilder: 6 umbrella+chair sets

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Generate break-zone seats scaled to the team size.
 *
 * Each zone gets at least its physical furniture count (8/8/6). For large
 * teams the 60% budget distributes proportionally (40/30/30). Pool is
 * always capped at 6 (physical umbrella sets).
 *
 * @param teamSize Number of org members (from snapshot).
 * @returns Array of BreakSeat with exact world-space positions.
 */
export function generateBreakSeats(teamSize: number): BreakSeat[] {
  const budget = Math.max(Math.ceil(teamSize * BREAK_RATIO), 6)

  // Each zone gets max(budget-share, physical-furniture-count).
  // Pool is computed first (capped), coffee second, cafeteria absorbs remainder.
  const poolCount = Math.min(Math.max(Math.floor(budget * 0.3), POOL_MIN), POOL_MAX)
  const cofCount = Math.max(Math.floor(budget * 0.3), COFFEE_MIN)
  const cafCount = Math.max(budget - cofCount - poolCount, CAFE_MIN)

  const caf  = requireZone("cafeteria")
  const cof  = requireZone("coffee_bar")
  const pool = requireZone("pool")

  return [
    ...seatsFromLayout(CAFETERIA_LAYOUT, caf.x, caf.z, cafCount),
    ...seatsFromLayout(COFFEE_BAR_LAYOUT, cof.x, cof.z, cofCount),
    ...generatePoolSeats(pool.x, pool.z, poolCount),
  ]
}

// ─── Zone layout engine ─────────────────────────────────────────────────────

/**
 * Convert a shared BreakZoneLayout into world-space seats for up to `count`
 * members. Count is clamped to the layout's physical seat count — the
 * frontend only draws `breakSeatCount(layout)` chairs, so emitting more
 * would put characters on thin air. To give more members a seat, add slots
 * to the shared layout (and both builders will render the extra furniture).
 *
 * Iteration order matches `forEachBreakSeat`, which the frontend builders
 * also follow — so seat index N on the server refers to the same physical
 * chair as seat index N on the client.
 */
function seatsFromLayout(
  layout: BreakZoneLayout, zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  const seats: BreakSeat[] = []
  const cap = Math.min(count, breakSeatCount(layout))
  forEachBreakSeat(layout, (idx, slot, chair) => {
    if (idx >= cap) return
    const yawRad = chair.yaw * Math.PI / 180
    seats.push({
      zone: layout.zone,
      x: zoneX + slot.x + chair.dx + Math.sin(yawRad) * layout.forwardOffset,
      y: layout.seatY,
      z: zoneZ + slot.z + chair.dz + Math.cos(yawRad) * layout.forwardOffset,
      yaw: chair.yaw,
    })
  })
  return seats
}

/**
 * Pool seats — procedural beach loungers around the pool.
 *
 * Seat height = DECK_TOP_Y (0.18) + ProceduralBeachChair.SEAT_HEIGHT (0.25).
 * The loungers are placed on top of the sandstone deck slabs built by
 * PoolResortBuilder, so characters sit at deck + chair height, not floor + chair.
 */
function generatePoolSeats(
  zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  // Must match PoolResortBuilder: DECK_TOP_Y (0.18) + SEAT_HEIGHT (0.25).
  // The server Y IS the character's final world Y (the frontend does
  // setPosition(x, y, z) directly — no deck correction happens after spawn).
  const SEAT_Y = 0.43

  const ALL_POOL_SEATS: BreakSeat[] = [
    { zone: "pool_resort", x: zoneX - 5,   y: SEAT_Y, z: zoneZ - 1.5, yaw: 90 },
    { zone: "pool_resort", x: zoneX - 5,   y: SEAT_Y, z: zoneZ + 2.5, yaw: 90 },
    { zone: "pool_resort", x: zoneX + 5,   y: SEAT_Y, z: zoneZ - 1.5, yaw: -90 },
    { zone: "pool_resort", x: zoneX + 5,   y: SEAT_Y, z: zoneZ + 2.5, yaw: -90 },
    { zone: "pool_resort", x: zoneX - 2.5, y: SEAT_Y, z: zoneZ + 5,   yaw: 180 },
    { zone: "pool_resort", x: zoneX + 2.5, y: SEAT_Y, z: zoneZ + 5,   yaw: 180 },
  ]
  return ALL_POOL_SEATS.slice(0, Math.min(count, POOL_MAX))
}
