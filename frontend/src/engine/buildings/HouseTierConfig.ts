/**
 * HouseTierConfig — House tier dimensions and unlock costs.
 *
 * Furniture layouts are NOT config-driven. The actual placement code uses
 * composite operations (stacking, SeatProber, AABB centering) that don't
 * reduce to a flat data array. Layout logic lives in HouseBuilder methods.
 *
 * This file defines only the structural dimensions and skill-point costs.
 */

export interface HouseTierDef {
  tier: number
  name: string
  width: number   // floor tiles (X axis)
  depth: number   // floor tiles (Z axis)
  unlockCost: number // skill points required (0 = free)
}

export const HOUSE_TIERS: readonly HouseTierDef[] = [
  { tier: 1, name: 'Hut',     width: 3, depth: 3, unlockCost: 0 },
  { tier: 2, name: 'Cottage',  width: 4, depth: 4, unlockCost: 0 },
  { tier: 3, name: 'Mansion',  width: 5, depth: 5, unlockCost: 100 },
]

/** Maximum footprint across all tiers — used for grid spacing calculation. */
export const MAX_TIER_FOOTPRINT = Math.max(...HOUSE_TIERS.map(t => Math.max(t.width, t.depth)))

export function getHouseTier(tier: number): HouseTierDef {
  return HOUSE_TIERS.find(t => t.tier === tier) ?? HOUSE_TIERS[1] // default to Cottage
}
