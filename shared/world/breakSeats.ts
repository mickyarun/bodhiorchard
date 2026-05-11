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
 * Single source of truth for break-zone seat layout (coffee bar + cafeteria).
 *
 * Imported by:
 *   - `frontend/src/engine/buildings/CoffeeBarBuilder.ts` — places the visible
 *     tables/chairs and builds InteractionPoints for local seating.
 *   - `frontend/src/engine/buildings/CafeteriaBuilder.ts` — same, with benches.
 *   - `multiplayer/src/sim/BreakSeatGenerator.ts` — emits world-space seat
 *     positions for remote members placed on break by the server.
 *
 * Coordinates are **zone-local** (x, z relative to the zone centre from
 * `zones.ts`). Seat Y is the character-hip world Y at rest on the chair.
 * The `forwardOffset` matches the per-furniture surface offset in
 * `frontend/src/engine/characters/InteractionPoint.ts` — it shifts the
 * character from the chair's AABB centre onto the actual sit surface.
 *
 * Iteration contract: `forEachBreakSeat` below is the ONLY loop either
 * side should use. Both frontend builders and the multiplayer generator
 * walk it in the same order, so seat indices line up 1:1.
 */

export interface TableSlot {
  x: number
  z: number
}

export interface ChairOffset {
  dx: number
  dz: number
  yaw: number
}

export interface BreakZoneLayout {
  /** Zone name matches `zones.ts` (`"coffee_bar"` or `"cafeteria"`). */
  zone: string
  tables: readonly TableSlot[]
  /** Seats per table. Usually 2 (facing chairs or opposing benches). */
  chairs: readonly ChairOffset[]
  /** World-space Y of the character's hips when sitting. */
  seatY: number
  /** AABB-centre → seat-surface forward offset in the chair's facing dir. */
  forwardOffset: number
}

// ─── Coffee bar ────────────────────────────────────────────────────────────
//
// Middle + far rows of small round tables, each with two facing chairs and
// a red umbrella. The near row directly in front of the door is deliberately
// empty so there's a clear walking corridor from door to patio.
//
// Right-column tables are pulled inward (+4.2 → +2.7 mid, +2.5 → +1.0 far)
// so the patio fits inside the 8-radius fence on the right.

export const COFFEE_BAR_LAYOUT: BreakZoneLayout = {
  zone: 'coffee_bar',
  tables: [
    { x: -4.2, z: 4.0 },
    { x:  2.7, z: 4.0 },
    { x: -2.5, z: 6.3 },
    { x:  1.0, z: 6.3 },
  ],
  chairs: [
    { dx: -0.8, dz: 0, yaw:  90 },
    { dx:  0.8, dz: 0, yaw: -90 },
  ],
  seatY: 0.23,          // chairCushion seatY from InteractionPoint.SEAT_OFFSETS
  forwardOffset: 0.15,  // chairCushion forwardOffset
}

// ─── Cafeteria ─────────────────────────────────────────────────────────────
//
// Two rows of picnic tables with benches on both long sides (benches, not
// chairs — the differentiator from the coffee bar).

export const CAFETERIA_LAYOUT: BreakZoneLayout = {
  zone: 'cafeteria',
  tables: [
    { x: -2.0, z: 2.0 },
    { x:  2.0, z: 2.0 },
    { x: -2.0, z: 5.0 },
    { x:  2.0, z: 5.0 },
  ],
  chairs: [
    { dx: 0, dz: -0.55, yaw:   0 },
    { dx: 0, dz:  0.55, yaw: 180 },
  ],
  seatY: 0.23,          // benchCushion seatY
  forwardOffset: 0.10,  // benchCushion forwardOffset
}

/**
 * Canonical seat-walking order — outer = table, inner = chair.
 *
 * Both the frontend builders and the multiplayer seat generator iterate
 * this so seat index N refers to the same physical chair on both sides.
 */
export function forEachBreakSeat(
  layout: BreakZoneLayout,
  visit: (seatIndex: number, slot: TableSlot, chair: ChairOffset) => void,
): void {
  let seatIndex = 0
  for (const slot of layout.tables) {
    for (const chair of layout.chairs) {
      visit(seatIndex++, slot, chair)
    }
  }
}

/** Total physical seat count for a zone (rows × chairs). */
export function breakSeatCount(layout: BreakZoneLayout): number {
  return layout.tables.length * layout.chairs.length
}
