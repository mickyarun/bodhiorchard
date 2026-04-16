/**
 * HouseTierConfig — House tier dimensions, costs, and exterior models.
 *
 * Tier 1 (Hut):     Default for all members. Kenney procedural house.
 * Tier 2 (Cottage):  KayKit home_medium.glb. Unlocked with 50 SP.
 * Tier 3 (Mansion):  KayKit home_barracks.glb. Unlocked with 100 SP.
 *
 * Furniture layouts are NOT config-driven. The actual placement code uses
 * composite operations (stacking, SeatProber, AABB centering) that don't
 * reduce to a flat data array. Layout logic lives in HouseBuilder methods.
 */

export interface HouseTierDef {
  tier: number
  name: string
  width: number   // floor tiles (X axis) — also the target exterior width for KayKit tiers (scaled to match)
  depth: number   // floor tiles (Z axis) — also the target exterior depth for KayKit tiers
  unlockCost: number // skill points required (0 = free)
  /** Tile index of the door on the front wall (interior AND exterior share this). */
  doorIndex: number
  /** If set, use this whole-building GLB instead of Kenney procedural walls+roof. */
  exteriorGlb?: string
  /**
   * Fallback scale for KayKit exterior models (default 1.0). Only used when
   * BuildingFactory.getEntityFootprint() returns 0 for a loaded GLB; normally
   * the scale is computed dynamically to fit the width × depth tile footprint.
   */
  exteriorScale?: number
  /**
   * Fallback raw GLB footprint (world units before scaling). Only used when
   * dynamic measurement fails. Normally superseded by the measured AABB.
   */
  exteriorFootprint?: { w: number; d: number }
}

export const HOUSE_TIERS: readonly HouseTierDef[] = [
  { tier: 1, name: 'Hut',     width: 3, depth: 3, doorIndex: 1, unlockCost: 0 },
  {
    tier: 2, name: 'Cottage',  width: 4, depth: 4, doorIndex: 1, unlockCost: 50,
    exteriorGlb: 'assets/buildings/kaykit/home_medium.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 2.2, d: 2.2 },
  },
  {
    tier: 3, name: 'Mansion',  width: 5, depth: 5, doorIndex: 2, unlockCost: 100,
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
