// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HouseTiers — pure tier geometry shared between frontend and multiplayer.
 *
 * Frontend's `HouseTierConfig.ts` extends this with render-only fields
 * (GLB paths, thumbnails, model scales) to produce the full per-tier record
 * its builders need. Multiplayer imports only from here — it never needs to
 * know which model a tier renders, just the floor plan and the seat positions.
 *
 * Coordinate convention: corner-local space (0,0 = back-left corner of the
 * house floor). X increases rightward along the front wall; Z increases
 * toward the front door.
 */

export interface HouseTierGeometry {
  tier: number
  /** Floor tile count along X. Also the target exterior width for KayKit tiers. */
  width: number
  /** Floor tile count along Z. Also the target exterior depth for KayKit tiers. */
  depth: number
  /** SP cost to unlock this tier (0 for the default). */
  unlockCost: number
  /** Tile index of the door on the front wall. Interior + exterior + physics all use this. */
  doorIndex: number
  /** Bed origin in corner-local space. */
  bed: { x: number; z: number }
  /** Desk chair position + facing in corner-local space. */
  desk: { x: number; z: number; yaw: number }
}

/** Bed mattress surface height — same for all tiers. */
export const BED_SURFACE_Y = 0.38

/** Desk chair seat surface height — same for all tiers. */
export const DESK_SEAT_Y = 0.15

export const HOUSE_TIER_GEOMETRIES: readonly HouseTierGeometry[] = [
  {
    tier: 1, width: 3, depth: 3, doorIndex: 1, unlockCost: 0,
    bed: { x: 1.0, z: 0.7 },
    desk: { x: 2.2, z: 1.3, yaw: 180 },
  },
  {
    tier: 2, width: 4, depth: 4, doorIndex: 1, unlockCost: 50,
    bed: { x: 1.0, z: 1.1 },
    desk: { x: 3.2, z: 1.3, yaw: 180 },
  },
  {
    tier: 3, width: 5, depth: 5, doorIndex: 2, unlockCost: 100,
    bed: { x: 1.5, z: 0.8 },
    desk: { x: 3.4, z: 1.3, yaw: 180 },
  },
  {
    tier: 4, width: 5, depth: 5, doorIndex: 2, unlockCost: 200,
    bed: { x: 1.5, z: 0.8 },
    desk: { x: 3.4, z: 1.3, yaw: 180 },
  },
]

/** Largest footprint across all tiers — used by layout grid spacing. */
export const MAX_TIER_FOOTPRINT = Math.max(
  ...HOUSE_TIER_GEOMETRIES.map(t => Math.max(t.width, t.depth)),
)

/**
 * Look up a tier's geometry. Falls back to tier 1 with a warning if the
 * caller asks for something not defined — this matches the previous
 * frontend behaviour and keeps the multiplayer server robust to stale
 * `house_level` values from the database.
 */
export function getHouseTierGeometry(tier: number): HouseTierGeometry {
  const found = HOUSE_TIER_GEOMETRIES.find(t => t.tier === tier)
  if (!found) {
    // eslint-disable-next-line no-console
    console.warn(
      `[HouseTiers] Unknown tier ${tier} — falling back to tier 1. ` +
      `If this is a new tier, add it to HOUSE_TIER_GEOMETRIES.`,
    )
  }
  return found ?? HOUSE_TIER_GEOMETRIES[0]
}
