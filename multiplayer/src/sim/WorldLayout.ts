// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * WorldLayout — Server-side layout helpers.
 *
 * Zone data (ZONES, Zone, getZone) comes from `@shared/world/zones` —
 * the SAME source the frontend uses. When you move a zone, edit
 * shared/world/zones.ts ONLY; both sides pick up the change.
 *
 * This file still owns server-specific layout math that mirrors
 * frontend/src/engine/buildings/VillageLayout.ts + HouseTierConfig.ts
 * (house placement, desk/bed seat positions). Those haven't been
 * shared yet; when they are, this file can shrink further.
 */

export { ZONES, getZone, type Zone } from "../../../shared/world/zones"
import { getZone } from "../../../shared/world/zones"

// ─── VillageLayout constants (mirror frontend/src/engine/buildings/VillageLayout.ts) ───

const HOUSE_SPACING_ALONG = 5.5
const ROW_OFFSET = 6
const STREET_GAP = 18
const HOUSES_PER_SIDE = 4
const HOUSES_PER_STREET = HOUSES_PER_SIDE * 2

/** Desk chair seat height — mirrors frontend HouseTierConfig.DESK_SEAT_Y. */
const DESK_SEAT_Y = 0.15
/** Bed mattress surface height — mirrors frontend HouseTierConfig.BED_SURFACE_Y. */
const BED_SURFACE_Y = 0.38

/**
 * ── Tier geometry (mirrors frontend/src/engine/buildings/HouseTierConfig.ts) ──
 *
 * Single source of truth is the frontend HouseTierConfig. These values MUST
 * stay in sync. When adding a new tier, update both files.
 *
 * Layout:  { width, depth, doorIndex, bed: {x,z}, desk: {x,z,yaw} }
 *   Tier 1 (Hut):     3×3, door=1, bed=(1.0, 0.7), desk=(2.2, 1.3, 180)
 *   Tier 2 (Cottage):  4×4, door=1, bed=(1.0, 1.1), desk=(3.2, 1.3, 180)
 *   Tier 3 (Mansion):  5×5, door=2, bed=(1.5, 0.8), desk=(3.4, 1.3, 180)
 *   Tier 4 (Villa):    5×5, door=2, bed=(1.5, 0.8), desk=(3.4, 1.3, 180)
 */
const TIER_CONFIG: Record<number, {
  width: number; depth: number
  bed: { x: number; z: number }
  desk: { x: number; z: number; yaw: number }
}> = {
  1: { width: 3, depth: 3, bed: { x: 1.0, z: 0.7 }, desk: { x: 2.2, z: 1.3, yaw: 180 } },
  2: { width: 4, depth: 4, bed: { x: 1.0, z: 1.1 }, desk: { x: 3.2, z: 1.3, yaw: 180 } },
  3: { width: 5, depth: 5, bed: { x: 1.5, z: 0.8 }, desk: { x: 3.4, z: 1.3, yaw: 180 } },
  4: { width: 5, depth: 5, bed: { x: 1.5, z: 0.8 }, desk: { x: 3.4, z: 1.3, yaw: 180 } },
}

/** Centering offset derived from width/depth — no longer hardcoded. */
function centerOffset(houseLevel: number): { x: number; z: number } {
  const c = TIER_CONFIG[houseLevel] ?? TIER_CONFIG[1]
  return { x: -c.width / 2, z: -c.depth / 2 }
}

/**
 * Compute the world-space position and rotation of a member's house.
 * Mirrors frontend VillageLayout.computeVillageLayout() exactly.
 * One road per street, houses on both sides facing inward.
 */
export function getHouseOrigin(
  memberIndex: number,
  totalMembers: number,
): { x: number; z: number; yawDeg: number } | null {
  const zone = getZone("housing")
  if (!zone || totalMembers === 0) return null

  const streetCount = Math.max(1, Math.ceil(totalMembers / HOUSES_PER_STREET))
  const totalDepth = (streetCount - 1) * STREET_GAP
  const baseZ = zone.z - totalDepth / 2

  const streetIdx = Math.floor(memberIndex / HOUSES_PER_STREET)
  const posInStreet = memberIndex % HOUSES_PER_STREET
  const streetStart = streetIdx * HOUSES_PER_STREET
  const membersOnStreet = Math.min(HOUSES_PER_STREET, totalMembers - streetStart)

  // Determine side
  let side: 'north' | 'south'
  if (membersOnStreet <= HOUSES_PER_SIDE) {
    side = 'north'
  } else {
    side = posInStreet % 2 === 0 ? 'north' : 'south'
  }

  // Count per side for X layout
  let northCount = 0, southCount = 0
  for (let i = streetStart; i < streetStart + membersOnStreet; i++) {
    const pos = i % HOUSES_PER_STREET
    if (membersOnStreet <= HOUSES_PER_SIDE) { northCount++ }
    else if (pos % 2 === 0) { northCount++ }
    else { southCount++ }
  }

  // Compute slot on this member's side
  let slotOnSide = 0
  for (let i = streetStart; i < memberIndex; i++) {
    const pos = i % HOUSES_PER_STREET
    const iSide = membersOnStreet <= HOUSES_PER_SIDE ? 'north' : (pos % 2 === 0 ? 'north' : 'south')
    if (iSide === side) slotOnSide++
  }

  const streetZ = baseZ + streetIdx * STREET_GAP
  const maxPerSide = Math.max(northCount, southCount)
  const rowWidth = (maxPerSide - 1) * HOUSE_SPACING_ALONG
  const startX = zone.x - rowWidth / 2

  return {
    x: startX + slotOnSide * HOUSE_SPACING_ALONG,
    z: side === 'north' ? streetZ - ROW_OFFSET : streetZ + ROW_OFFSET,
    yawDeg: side === 'north' ? 0 : 180,
  }
}

/**
 * Compute world-space desk seat position for a member's house.
 * Applies centering offset (corner → center) then house rotation.
 */
export function getHouseDeskSeat(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  const cfg = TIER_CONFIG[houseLevel] ?? TIER_CONFIG[1]
  const offset = centerOffset(houseLevel)
  const cx = offset.x + cfg.desk.x
  const cz = offset.z + cfg.desk.z
  const rad = origin.yawDeg * Math.PI / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)

  return {
    x: origin.x + cx * cos + cz * sin,
    y: DESK_SEAT_Y,
    z: origin.z - cx * sin + cz * cos,
    yaw: cfg.desk.yaw + origin.yawDeg,
  }
}

/**
 * Compute world-space bed position for a member's house.
 * Applies centering offset (corner → center) then house rotation.
 */
export function getHouseBedPosition(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  const cfg = TIER_CONFIG[houseLevel] ?? TIER_CONFIG[1]
  const offset = centerOffset(houseLevel)
  const cx = offset.x + cfg.bed.x
  const cz = offset.z + cfg.bed.z
  const rad = origin.yawDeg * Math.PI / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)

  return {
    x: origin.x + cx * cos + cz * sin,
    y: BED_SURFACE_Y,
    z: origin.z - cx * sin + cz * cos,
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

// Break zone seats are now generated dynamically by BreakSeatGenerator.ts
// based on team size. See generateBreakSeats(teamSize) for the layout
// engines that mirror the frontend builders' exact furniture positions.
