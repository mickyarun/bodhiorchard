// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * WorldLayout — Server-side layout helpers.
 *
 * All the math here is now thin wrappers around the shared layout + geometry
 * in `shared/world/VillageLayout.ts` and `shared/world/HouseTiers.ts`. This
 * file's job is purely to:
 *   1. Memoise the village layout per (zone, totalMembers) so per-member
 *      getters don't re-run the algorithm.
 *   2. Apply the housing zone's rotation to house origins and interior
 *      seat positions before returning world-space coordinates.
 *
 * When tier geometry or the village algorithm changes, there is no second
 * file to update.
 */

import {
  computeVillageLayout,
  type VillageLayoutResult,
} from "../../../shared/world/VillageLayout"
import { rotatePointAroundPivot, toWorld } from "../../../shared/world/geom"
import {
  getHouseTierGeometry,
  BED_SURFACE_Y,
  DESK_SEAT_Y,
} from "../../../shared/world/HouseTiers"

export { ZONES, getZone, type Zone } from "../../../shared/world/zones"
import { getZone, type Zone } from "../../../shared/world/zones"

// ─── Layout memoisation ─────────────────────────
//
// Placements are count-pure (see computeVillageLayout docs): they depend
// only on totalMembers and the zone. Key on a stable signature so distinct
// zones and rotations get distinct entries. If zone coords change at
// runtime (they don't today), the key changes and the cache naturally
// repopulates on the next call.
const layoutCache = new Map<string, VillageLayoutResult>()

function cacheKey(zone: Zone, totalMembers: number): string {
  return `${zone.name}|${zone.x}|${zone.z}|${zone.yawDeg ?? 0}|${totalMembers}`
}

/**
 * Exported so a test harness or future live-reload can flush the cache
 * without reaching into the module's private state.
 */
export function resetVillageLayoutCache(): void {
  layoutCache.clear()
}

function getHousingLayout(totalMembers: number): VillageLayoutResult | null {
  const zone = getZone("housing")
  if (!zone || totalMembers <= 0) return null
  const key = cacheKey(zone, totalMembers)
  let cached = layoutCache.get(key)
  if (!cached) {
    // Shape the members[] to exactly what computeVillageLayout needs — the
    // placement math is count-pure, so real user_id/name never matter here.
    const members = Array.from({ length: totalMembers }, (_, i) => ({
      user_id: `m${i}`, name: `m${i}`,
    }))
    cached = computeVillageLayout(members, zone)
    layoutCache.set(key, cached)
  }
  return cached
}

// ─── Public API (unchanged signatures) ───────────

/**
 * Compute world-space origin + yaw for a member's house.
 *
 * Returns null if the housing zone is missing or totalMembers is 0.
 * Callers (MemberPlacement) already handle null by falling back to garden.
 */
export function getHouseOrigin(
  memberIndex: number,
  totalMembers: number,
): { x: number; z: number; yawDeg: number } | null {
  const layout = getHousingLayout(totalMembers)
  if (!layout) return null
  const placement = layout.placements[memberIndex]
  if (!placement) return null
  const zone = getZone("housing")
  if (!zone) return null
  // Placement is LOCAL (yaw-free, centred on 0,0) — rotate around the zone
  // centre and translate to world. House-yaw composes with zone-yaw so
  // front-of-house stays facing the rotated road.
  const world = rotatePointAroundPivot(
    placement.x + zone.x, placement.z + zone.z, layout.yawRad, zone.x, zone.z,
  )
  return {
    x: world.x,
    z: world.z,
    yawDeg: placement.yawDeg + (zone.yawDeg ?? 0),
  }
}

/**
 * Compute world-space desk seat position for a member's house.
 * Applies the house's corner → centre offset (tile-local) then the
 * composed house+village rotation.
 */
export function getHouseDeskSeat(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null
  const geom = getHouseTierGeometry(houseLevel)
  // Desk is corner-local; shift to house-centre space (matches HouseBuilder's
  // pivot, which centres the rendered tile footprint on the placement).
  const cx = geom.desk.x - geom.width / 2
  const cz = geom.desk.z - geom.depth / 2
  const world = toWorld({ x: cx, z: cz }, { x: origin.x, z: origin.z, yawDeg: origin.yawDeg })
  return {
    x: world.x,
    y: DESK_SEAT_Y,
    z: world.z,
    yaw: geom.desk.yaw + origin.yawDeg,
  }
}

/**
 * Compute world-space bed position for a member's house. Same transform
 * chain as `getHouseDeskSeat` — the bed is just a different corner-local
 * point within the same tile.
 */
export function getHouseBedPosition(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null
  const geom = getHouseTierGeometry(houseLevel)
  const cx = geom.bed.x - geom.width / 2
  const cz = geom.bed.z - geom.depth / 2
  const world = toWorld({ x: cx, z: cz }, { x: origin.x, z: origin.z, yawDeg: origin.yawDeg })
  return {
    x: world.x,
    y: BED_SURFACE_Y,
    z: world.z,
    yaw: origin.yawDeg,
  }
}

// ─── Tree positions (repo trees in orchard) ─────
// Re-export from shared so client + server agree byte-for-byte.
export {
  getTreePositions,
  getAgentSlotAtTree,
  getAgentFallbackSlot,
} from "../../../shared/world/treePositions"

// Break zone seats are generated dynamically by BreakSeatGenerator.ts
// based on team size. See generateBreakSeats(teamSize) for the layout
// engines that mirror the frontend builders' exact furniture positions.
