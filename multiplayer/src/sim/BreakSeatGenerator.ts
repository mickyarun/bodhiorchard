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

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Generate break-zone seats scaled to the team size.
 *
 * Distribution: 40% cafeteria, 30% coffee bar, 30% pool (capped at 6).
 * Any pool overflow redistributes to cafeteria (largest capacity).
 *
 * @param teamSize Number of org members (from snapshot).
 * @returns Array of BreakSeat with exact world-space positions.
 */
export function generateBreakSeats(teamSize: number): BreakSeat[] {
  const budget = Math.max(Math.ceil(teamSize * BREAK_RATIO), 6) // min 6

  // Split: pool gets 30% (capped), coffee bar gets 30%, cafeteria gets remainder.
  // Using floor for pool + coffee and giving the remainder to cafeteria avoids
  // the ceil-on-each-split overcount that produces more seats than the budget.
  const poolCount = Math.min(Math.floor(budget * 0.3), POOL_MAX)
  const cofCount = Math.floor(budget * 0.3)
  const cafCount = budget - cofCount - poolCount

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
 */
function generateCafeteriaSeats(
  zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  const BENCH_OFFSET = 0.55
  const ROW_START_Z = 3.5
  const ROW_SPACING = 2.8
  const TABLE_XS = [1.0, 3.0]
  const SEAT_Y = 0.23

  const seats: BreakSeat[] = []
  const rows = Math.ceil(count / 4)

  for (let row = 0; row < rows; row++) {
    const tz = ROW_START_Z + row * ROW_SPACING
    for (const tableX of TABLE_XS) {
      for (const side of [-1, 1]) {
        if (seats.length >= count) return seats
        seats.push({
          zone: "cafeteria",
          x: zoneX + tableX,
          y: SEAT_Y,
          z: zoneZ + tz + side * BENCH_OFFSET,
          yaw: side > 0 ? 180 : 0,
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

  const seats: BreakSeat[] = []
  const tablesPerCol = Math.ceil(count / 4) // 4 seats per 2 columns
  // Ensure at least 1 table per column to avoid empty zones
  const maxTables = Math.max(tablesPerCol, 1)

  for (let t = 0; t < maxTables; t++) {
    const tz = TABLE_START_Z + t * TABLE_SPACING
    for (const col of COLUMNS) {
      if (seats.length >= count) return seats
      seats.push({
        zone: "coffee_bar",
        x: zoneX + col.baseX + col.leftOffset,
        y: SEAT_Y,
        z: zoneZ + tz,
        yaw: 90,
      })
      if (seats.length >= count) return seats
      seats.push({
        zone: "coffee_bar",
        x: zoneX + col.baseX + col.rightOffset,
        y: SEAT_Y,
        z: zoneZ + tz,
        yaw: -90,
      })
    }
  }
  return seats
}

/**
 * Pool seats — mirrors PoolResortBuilder.ts layout.
 *
 * Fixed positions around the pond (6 umbrella+chair sets). The pool
 * doesn't scale dynamically because each seat needs a visible umbrella
 * GLB set — adding more requires a frontend builder change.
 */
function generatePoolSeats(
  zoneX: number, zoneZ: number, count: number,
): BreakSeat[] {
  const SEAT_Y = 0.15
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
