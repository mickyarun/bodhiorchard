// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HouseTierConfig — Single source of truth for house tier geometry.
 *
 * Every position that needs to stay in sync between frontend (HouseBuilder,
 * TakeoverPhysicsBuilder, InteriorManager) and multiplayer (WorldLayout) is
 * defined here. Adding a new tier = one new entry in HOUSE_TIERS; all
 * consuming code derives from it automatically.
 *
 * Tier 1 (Hut):     Default. KayKit home_small.glb.
 * Tier 2 (Cottage):  KayKit home_medium.glb. Unlocked with 50 SP.
 * Tier 3 (Mansion):  KayKit home_barracks.glb. Unlocked with 100 SP.
 * Tier 4 (Villa):    Kenney procedural modern building. Unlocked with 200 SP.
 *
 * Coordinate system: corner-local space (0,0 = back-left corner of the
 * house floor). X increases rightward, Z increases toward the front door.
 */

export interface HouseTierDef {
  tier: number
  name: string
  /** Floor tile count along X. Also the target exterior width for KayKit tiers. */
  width: number
  /** Floor tile count along Z. Also the target exterior depth for KayKit tiers. */
  depth: number
  unlockCost: number
  /** Tile index of the door on the front wall (interior AND exterior share this). */
  doorIndex: number
  /** Bed position in corner-local space (X, Z). Used by HouseBuilder + multiplayer NPC sim. */
  bed: { x: number; z: number }
  /** Desk chair position + facing in corner-local space. Used by HouseBuilder + multiplayer NPC sim. */
  desk: { x: number; z: number; yaw: number }
  /** Preview thumbnail for the upgrade shop UI. Path relative to /public. */
  thumbnail: string
  /** If set, use this whole-building GLB instead of Kenney procedural walls+roof. */
  exteriorGlb?: string
  /** Fallback scale for KayKit exterior models (used only when AABB measurement fails). */
  exteriorScale?: number
  /** Fallback raw GLB footprint in world units before scaling (used only when measurement fails). */
  exteriorFootprint?: { w: number; d: number }
}

/** Bed mattress surface height — same for all tiers. */
export const BED_SURFACE_Y = 0.38

/** Desk chair seat surface height — same for all tiers. */
export const DESK_SEAT_Y = 0.15

export const HOUSE_TIERS: readonly HouseTierDef[] = [
  {
    tier: 1, name: 'Hut', width: 3, depth: 3, doorIndex: 1, unlockCost: 0,
    bed: { x: 1.0, z: 0.7 },
    desk: { x: 2.2, z: 1.3, yaw: 180 },
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_small.png',
    exteriorGlb: 'assets/buildings/kaykit/home_small.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 1.8, d: 1.8 },
  },
  {
    tier: 2, name: 'Cottage', width: 4, depth: 4, doorIndex: 1, unlockCost: 50,
    bed: { x: 1.0, z: 1.1 },
    desk: { x: 3.2, z: 1.3, yaw: 180 },
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_medium.png',
    exteriorGlb: 'assets/buildings/kaykit/home_medium.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 2.2, d: 2.2 },
  },
  {
    tier: 3, name: 'Mansion', width: 5, depth: 5, doorIndex: 2, unlockCost: 100,
    bed: { x: 1.5, z: 0.8 },
    desk: { x: 3.4, z: 1.3, yaw: 180 },
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_barracks.png',
    exteriorGlb: 'assets/buildings/kaykit/home_barracks.glb',
    exteriorScale: 1.8,
    exteriorFootprint: { w: 3.0, d: 3.0 },
  },
  {
    tier: 4, name: 'Villa', width: 5, depth: 5, doorIndex: 2, unlockCost: 200,
    bed: { x: 1.5, z: 0.8 },
    desk: { x: 3.4, z: 1.3, yaw: 180 },
    thumbnail: 'assets/buildings/kaykit/thumbnails/villa.png',
  },
]

/** Maximum footprint across all tiers — used for grid spacing calculation. */
export const MAX_TIER_FOOTPRINT = Math.max(...HOUSE_TIERS.map(t => Math.max(t.width, t.depth)))

export function getHouseTier(tier: number): HouseTierDef {
  const found = HOUSE_TIERS.find(t => t.tier === tier)
  if (!found) {
    console.warn(`[HouseTierConfig] Unknown tier ${tier} — falling back to tier 1 (Hut). ` +
      `If this is a new tier, add it to HOUSE_TIERS.`)
  }
  return found ?? HOUSE_TIERS[0]
}

