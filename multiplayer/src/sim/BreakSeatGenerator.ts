// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * BreakSeatGenerator — programmatic break-zone seat computation.
 *
 * Generates seat positions for cafeteria, coffee bar, and pool zones
 * using the **same layout constants** as the frontend builders
 * (CafeteriaBuilder, CoffeeBarBuilder, PoolResortBuilder). This ensures
 * server-placed characters sit at exactly the same world-space positions
 * as the visible furniture.
 *
 * Scaling: targets ~60% of team size across all break zones so multiple
 * members can take breaks simultaneously without overlapping. The pool
 * is capped at 6 (physical umbrella sets); cafeteria and coffee bar
 * grow by adding rows of tables.
 *
 * Zone positions are imported from the shared ZONES array — the same
 * source of truth as the frontend's WorldLayout.
 */

import { getZone } from "./WorldLayout"

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
 * each frontend builder. You can't have fewer seats than visible chairs,
 * or characters sit on air. For large teams the budget-based scaling
 * adds MORE rows; these minimums only kick in for small teams.
 */
const CAFE_MIN = 8     // CafeteriaBuilder: 2 rows × 2 tables × 2 benches
const COFFEE_MIN = 8   // CoffeeBarBuilder: 2 columns × 2 tables × 2 chairs
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

  const caf  = getZone("cafeteria")!
  const cof  = getZone("coffee_bar")!
  const pool = getZone("pool")!

  return [
    ...generateCafeteriaSeats(caf.x, caf.z, cafCount),
    ...generateCoffeeBarSeats(cof.x, cof.z, cofCount),
    ...generatePoolSeats(pool.x, pool.z, poolCount),
  ]
}

// ─── Zone layout engines ────────────────────────────────────────────────────

/**
 * Cafeteria seats — mirrors CafeteriaBuilder.ts layout.
 *
 * Layout: rows of 2 long tables, each with a bench on both sides.
 * 4 seats per row (2 tables × 2 sides). Rows spaced 2.8 units apart.
 * First row starts at local z=3.5 (in front of the kitchen hut).
 *
 * Iteration order: outer=side, inner=tableX — must match
 * CafeteriaBuilder.ts so seat indices align for occupancy tracking.
 */
function generateCafeteriaSeats(
  zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  const BENCH_OFFSET = 0.55
  const ROW_START_Z = 3.5
  const ROW_SPACING = 2.8
  const TABLE_XS = [1.0, 3.0]
  const SEAT_Y = 0.23
  // Must match SEAT_OFFSETS.benchCushion.forwardOffset in
  // frontend/src/engine/characters/InteractionPoint.ts
  const FORWARD_OFFSET = 0.10

  const seats: BreakSeat[] = []
  const rows = Math.ceil(count / 4)

  for (let row = 0; row < rows; row++) {
    const tz = ROW_START_Z + row * ROW_SPACING
    for (const side of [-1, 1]) {
      const yaw = side > 0 ? 180 : 0
      const yawRad = yaw * Math.PI / 180
      for (const tableX of TABLE_XS) {
        if (seats.length >= count) return seats
        seats.push({
          zone: "cafeteria",
          x: zoneX + tableX + Math.sin(yawRad) * FORWARD_OFFSET,
          y: SEAT_Y,
          z: zoneZ + tz + side * BENCH_OFFSET + Math.cos(yawRad) * FORWARD_OFFSET,
          yaw,
        })
      }
    }
  }
  return seats
}

/**
 * Coffee bar seats — mirrors CoffeeBarBuilder.ts layout.
 *
 * Layout: 2 columns of small round tables, each with 2 facing chairs.
 * Left column at localX=-1.0 (chairs at -1.8 and -0.2).
 * Right column at localX=2.5 (chairs at 1.7 and 3.3).
 * Tables spaced 2.0 units apart, starting at local z=3.5.
 *
 * Iteration order: outer=column, inner=table — must match
 * CoffeeBarBuilder.ts so seat indices align for occupancy tracking.
 */
function generateCoffeeBarSeats(
  zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  const COLUMNS = [
    { baseX: -1.0, leftOffset: -0.8, rightOffset: 0.8 },
    { baseX:  2.5, leftOffset: -0.8, rightOffset: 0.8 },
  ]
  const TABLE_START_Z = 3.5
  const TABLE_SPACING = 2.0
  const SEAT_Y = 0.23
  // Must match SEAT_OFFSETS.chairCushion.forwardOffset in
  // frontend/src/engine/characters/InteractionPoint.ts
  const FORWARD_OFFSET = 0.15

  const seats: BreakSeat[] = []
  const tablesPerCol = Math.ceil(count / 4) // 4 seats per 2 columns
  const maxTables = Math.max(tablesPerCol, 1)

  for (const col of COLUMNS) {
    for (let t = 0; t < maxTables; t++) {
      const tz = TABLE_START_Z + t * TABLE_SPACING
      if (seats.length >= count) return seats
      // Left chair (facing right, yaw=90)
      seats.push({
        zone: "coffee_bar",
        x: zoneX + col.baseX + col.leftOffset + Math.sin(90 * Math.PI / 180) * FORWARD_OFFSET,
        y: SEAT_Y,
        z: zoneZ + tz + Math.cos(90 * Math.PI / 180) * FORWARD_OFFSET,
        yaw: 90,
      })
      if (seats.length >= count) return seats
      // Right chair (facing left, yaw=-90)
      seats.push({
        zone: "coffee_bar",
        x: zoneX + col.baseX + col.rightOffset + Math.sin(-90 * Math.PI / 180) * FORWARD_OFFSET,
        y: SEAT_Y,
        z: zoneZ + tz + Math.cos(-90 * Math.PI / 180) * FORWARD_OFFSET,
        yaw: -90,
      })
    }
  }
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
