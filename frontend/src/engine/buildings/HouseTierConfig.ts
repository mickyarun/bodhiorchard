/**
 * HouseTierConfig — Single source of truth for house tier geometry.
 *
 * Every position that needs to stay in sync between frontend (HouseBuilder,
 * TakeoverPhysicsBuilder, InteriorManager) and multiplayer (WorldLayout) is
 * defined here. Adding a new tier = one new entry in HOUSE_TIERS; all
 * consuming code derives from it automatically.
 *
 * Tier 1 (Hut):     Default for all members. Kenney procedural house.
 * Tier 2 (Cottage):  KayKit home_medium.glb. Unlocked with 50 SP.
 * Tier 3 (Mansion):  KayKit home_barracks.glb. Unlocked with 100 SP.
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
  /** If set, use this whole-building GLB instead of Kenney procedural walls+roof. */
  exteriorGlb?: string
  /** Fallback scale for KayKit exterior models (used only when AABB measurement fails). */
  exteriorScale?: number
  /** Fallback raw GLB footprint in world units before scaling (used only when measurement fails). */
  exteriorFootprint?: { w: number; d: number }
}

/** Bed mattress surface height — same for all tiers. */
export const BED_SURFACE_Y = 0.38

export const HOUSE_TIERS: readonly HouseTierDef[] = [
  {
    tier: 1, name: 'Hut', width: 3, depth: 3, doorIndex: 1, unlockCost: 0,
    bed: { x: 1.0, z: 0.7 },
    desk: { x: 2.2, z: 1.3, yaw: 180 },
  },
  {
    tier: 2, name: 'Cottage', width: 4, depth: 4, doorIndex: 1, unlockCost: 50,
    bed: { x: 1.0, z: 1.1 },
    desk: { x: 3.2, z: 1.3, yaw: 180 },
    exteriorGlb: 'assets/buildings/kaykit/home_medium.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 2.2, d: 2.2 },
  },
  {
    tier: 3, name: 'Mansion', width: 5, depth: 5, doorIndex: 2, unlockCost: 100,
    bed: { x: 1.5, z: 0.8 },
    desk: { x: 3.4, z: 1.3, yaw: 180 },
    exteriorGlb: 'assets/buildings/kaykit/home_barracks.glb',
    exteriorScale: 1.8,
    exteriorFootprint: { w: 3.0, d: 3.0 },
  },
]

/** Maximum footprint across all tiers — used for grid spacing calculation. */
export const MAX_TIER_FOOTPRINT = Math.max(...HOUSE_TIERS.map(t => Math.max(t.width, t.depth)))

export function getHouseTier(tier: number): HouseTierDef {
  return HOUSE_TIERS.find(t => t.tier === tier) ?? HOUSE_TIERS[0] // default to Hut
}

/**
 * Compute corner-local exit position from tier config. Derived — not stored.
 * x = door center, z = 1 unit past front wall, yaw = 0 (facing away).
 */
export function getTierExitLocal(tier: HouseTierDef): { x: number; z: number; yaw: number } {
  return { x: tier.doorIndex + 0.5, z: tier.depth + 1.0, yaw: 0 }
}

/**
 * Centering offset: corner-origin → center-origin. Derived from width/depth.
 * Used by HousingVillage.wrapWithPivot and multiplayer WorldLayout.
 */
export function getTierCenterOffset(tier: HouseTierDef): { x: number; z: number } {
  return { x: -tier.width / 2, z: -tier.depth / 2 }
}
