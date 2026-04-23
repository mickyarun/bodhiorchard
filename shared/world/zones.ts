// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Single source of truth for world zone positions.
 *
 * Imported by:
 *   - `frontend/src/engine/world/WorldLayout.ts` — renders zones + builds paths/trees
 *   - `multiplayer/src/sim/WorldLayout.ts` — computes server-side seat placement
 *
 * To move a zone, edit this file ONLY. Both frontend and multiplayer will
 * pick up the new coordinates on next build — no character position
 * adjustments needed anywhere else.
 *
 * Tier semantics drive downstream visual choices (path primary/secondary,
 * tree framing bands, prop scatter annulus). Keep tiers consistent with
 * compositional intent:
 *   - hub        — the focal center (orchard). Exactly one.
 *   - activity   — inner ring the player walks through (coffee_bar,
 *                  cafeteria, pavilion). Typically 3 at 120° around hub.
 *   - habitation — outer "backdrop" infrastructure (housing, pool).
 */

export type ZoneTier = 'hub' | 'activity' | 'habitation'

export interface Zone {
  name: string
  tier: ZoneTier
  x: number
  z: number
  radius: number
  /**
   * Optional yaw (degrees) for zones whose interior layout is rectangular
   * and should read diagonally instead of axis-aligned. The frontend rotates
   * the zone's root entity by this value; the multiplayer server applies the
   * same rotation to any position it returns for that zone. Default is 0.
   */
  yawDeg?: number
}

/**
 * Housing diagonal yaw — a deliberate ~25° clockwise rotation so the
 * rectangular village reads "off-axis" to the cardinal activity ring.
 * Half of 45° would be quadrant-symmetric and feel contrived; 25° lands
 * at a natural-looking tilt without aligning with the zone's radial.
 */
export const HOUSING_YAW_DEG = -25

/**
 * Tiered-ring composition:
 *   - hub        at (0,0), r=18   — holds the HubAnchor + repo trees
 *   - activity   on inner ring at r≈28 from origin, 3 zones at 120°
 *   - habitation on outer ring at r≈46-50, behind the tree belt
 *
 * Housing centre derivation (for context on the (-44, 52) choice):
 *   - coffee_bar centre = (-26, 10), radius = 8
 *   - housing half-extent at 20 members (computed by VillageLayout) ≈ 19
 *   - safety margin 4u → need ≥ 8 + 19 + 4 = 31u clearance from coffee_bar
 *   - (-44, 52): centre-to-centre ≈ 46u → 24u clearance at 20 members, >10u through 30.
 */
export const ZONES: Zone[] = [
  { name: 'orchard',    tier: 'hub',        x: 0,    z: 0,    radius: 18 },
  { name: 'pavilion',   tier: 'activity',   x: 0,    z: -28,  radius: 6 },
  { name: 'coffee_bar', tier: 'activity',   x: -26,  z: 10,   radius: 8 },
  { name: 'cafeteria',  tier: 'activity',   x: 26,   z: 10,   radius: 8 },
  { name: 'housing',    tier: 'habitation', x: -44,  z: 52,   radius: 14, yawDeg: HOUSING_YAW_DEG },
  { name: 'pool',       tier: 'habitation', x: 30,   z: 40,   radius: 10 },
]

/** Get a zone by name. Returns null if not found. */
export function getZone(name: string): Zone | null {
  return ZONES.find(z => z.name === name) ?? null
}
