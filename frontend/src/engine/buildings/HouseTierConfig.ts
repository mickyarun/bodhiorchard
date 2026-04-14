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
  width: number   // floor tiles (X axis) — Kenney procedural; unused for KayKit
  depth: number   // floor tiles (Z axis) — Kenney procedural; unused for KayKit
  unlockCost: number // skill points required (0 = free)
  /** If set, use this whole-building GLB instead of Kenney procedural walls+roof. */
  exteriorGlb?: string
  /** Scale for KayKit exterior models (default 1.0). */
  exteriorScale?: number
  /** Raw GLB footprint (world units before scaling). Used for collision + label height. */
  exteriorFootprint?: { w: number; d: number }
}

export const HOUSE_TIERS: readonly HouseTierDef[] = [
  { tier: 1, name: 'Hut',     width: 3, depth: 3, unlockCost: 0 },
  {
    tier: 2, name: 'Cottage',  width: 4, depth: 4, unlockCost: 50,
    exteriorGlb: 'assets/buildings/kaykit/home_medium.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 2.2, d: 2.2 },
  },
  {
    tier: 3, name: 'Mansion',  width: 5, depth: 5, unlockCost: 100,
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
