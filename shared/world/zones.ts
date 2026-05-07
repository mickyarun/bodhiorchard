// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Single source of truth for world zone positions.
 *
 * Imported by:
 *   - `frontend/src/engine/world/WorldLayout.ts` — renders zones + builds paths/trees
 *   - `multiplayer/src/sim/WorldLayout.ts` — computes server-side seat placement
 *
 * Zone positions are derived from declarative `ZONE_DECLS` (each holds the
 * zone's *baseline* (x,z) — the literal coordinates that lived here before
 * sub-step 1b). At resolution time `buildZone` recovers polar form
 * `(angleRad, gapFromOrchardRim)` and applies the active orchard radius
 * from `LayoutScale`. At baseline this is a no-op recompute → coordinates
 * match the previous static `ZONES` array to floating-point precision.
 *
 * Phase 2: when `LayoutScale.orchardRadius` diverges from the baseline,
 * non-hub zones translate outward keeping the gap constant (keeping the
 * orchard rim → zone rim distance stable). The "inner only" propagation
 * rule from the plan; revisit `buildZone` when other rules are wanted.
 *
 * Tier semantics drive downstream visual choices (path primary/secondary,
 * tree framing bands, prop scatter annulus). Keep tiers consistent with
 * compositional intent:
 *   - hub        — the focal center (orchard). Exactly one.
 *   - activity   — inner ring the player walks through (coffee_bar,
 *                  cafeteria, pavilion). Typically 3 at 120° around hub.
 *   - habitation — outer "backdrop" infrastructure (housing, pool).
 */

import {
  BASELINE_ORCHARD_RADIUS,
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  onScaleChange,
  type LayoutScale,
} from './layoutScale'

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
 * Declarative zone form. `baselineX` / `baselineZ` are the literal
 * coordinates this zone occupied before sub-step 1b — preserved here as
 * the canonical reference for back-derivation (angle + gap-from-rim).
 */
export interface ZoneDecl {
  name: string
  tier: ZoneTier
  baselineX: number
  baselineZ: number
  radius: number
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
 * Tiered-ring composition (baseline coordinates):
 *   - hub        at (0,0), r=18   — holds the HubAnchor + repo trees
 *   - activity   inner ring 3 zones (pavilion south, coffee/cafeteria flanks)
 *   - habitation outer ring 2 zones (housing diagonal, pool offset)
 *
 * Housing centre derivation (for context on (-44, 52)):
 *   - coffee_bar centre = (-26, 10), radius = 8
 *   - housing half-extent at 20 members (computed by VillageLayout) ≈ 19
 *   - safety margin 4u → need ≥ 8 + 19 + 4 = 31u clearance from coffee_bar
 *   - (-44, 52): centre-to-centre ≈ 46u → 24u clearance at 20 members, >10u through 30.
 */
export const ZONE_DECLS: ZoneDecl[] = [
  { name: 'orchard',    tier: 'hub',        baselineX: 0,   baselineZ: 0,   radius: BASELINE_ORCHARD_RADIUS },
  { name: 'pavilion',   tier: 'activity',   baselineX: 0,   baselineZ: -28, radius: 6 },
  { name: 'coffee_bar', tier: 'activity',   baselineX: -26, baselineZ: 10,  radius: 8 },
  { name: 'cafeteria',  tier: 'activity',   baselineX: 26,  baselineZ: 10,  radius: 8 },
  { name: 'housing',    tier: 'habitation', baselineX: -44, baselineZ: 52,  radius: 14, yawDeg: HOUSING_YAW_DEG },
  { name: 'pool',       tier: 'habitation', baselineX: 30,  baselineZ: 40,  radius: 10 },
]

/**
 * Resolve a single zone declaration against the given scale.
 *
 * The hub zone trivially anchors at the origin and inherits
 * `scale.orchardRadius`. Non-hub zones recover polar form (angle, gap)
 * from their baseline coords, then translate outward as the orchard
 * grows so the gap-from-rim is preserved.
 */
export function buildZone(decl: ZoneDecl, scale: LayoutScale): Zone {
  if (decl.tier === 'hub') {
    return {
      name: decl.name,
      tier: decl.tier,
      x: 0,
      z: 0,
      radius: scale.orchardRadius,
      yawDeg: decl.yawDeg,
    }
  }
  const angleRad = Math.atan2(decl.baselineZ, decl.baselineX)
  const baselineDist = Math.hypot(decl.baselineX, decl.baselineZ)
  const gapFromOrchardRim = baselineDist - BASELINE_ORCHARD_RADIUS - decl.radius
  const dist = scale.orchardRadius + gapFromOrchardRim + decl.radius
  return {
    name: decl.name,
    tier: decl.tier,
    x: Math.cos(angleRad) * dist,
    z: Math.sin(angleRad) * dist,
    radius: decl.radius,
    yawDeg: decl.yawDeg,
  }
}

/** Resolve all zone declarations against the given scale. */
export function buildZones(scale: LayoutScale): Zone[] {
  return ZONE_DECLS.map(d => buildZone(d, scale))
}

/**
 * Internally-held resolved zone array. Replaced atomically via
 * `onScaleChange` so readers never see a transient half-state. External
 * code reads through `getZones()` (a `ReadonlyArray<Zone>`); the
 * mutability and reassignment live behind that boundary.
 *
 * The earlier `export const ZONES` exposed the array directly and
 * rebuilt via `length = 0; push(...)`, leaving a brief window where any
 * sync iteration during the listener saw an empty array. Baseline-only
 * scale today made the bug invisible; Phase 2 scale changes would have
 * exposed it.
 *
 * Initial seed is built directly from baseline — *not* via the active-scale
 * cache — so this module's load order does not depend on whether some
 * other module has already wired the cache. The first `setActiveScale`
 * call (frontend `WorldLayout` boot wire, multiplayer `sim/WorldLayout`
 * boot wire, etc.) fires the listener below and atomically swaps in the
 * resolved zone array for the live scale.
 */
let currentZones: ReadonlyArray<Zone> = buildZones(
  computeLayoutScale(BASELINE_REPO_COUNT),
)

onScaleChange(scale => {
  currentZones = buildZones(scale)
})

/**
 * Read-only view of the resolved zones. Always reflects the current
 * scale — call this fresh each time rather than caching the reference.
 */
export function getZones(): ReadonlyArray<Zone> {
  return currentZones
}

/** Get a zone by name. Returns null if not found. */
export function getZone(name: string): Zone | null {
  return currentZones.find(z => z.name === name) ?? null
}

/**
 * Get a zone by name or throw — use when the zone is a hard invariant of
 * the call site. Replaces the `getZone(name)!` non-null-assertion pattern
 * which converted "config bug" into a cryptic null-deref far from the
 * actual cause. Throws a named error pinpointing the missing zone.
 */
export function requireZone(name: string): Zone {
  const zone = getZone(name)
  if (!zone) {
    throw new Error(
      `[zones] requireZone('${name}') failed — no zone with this name in ` +
      `ZONE_DECLS (see shared/world/zones.ts).`,
    )
  }
  return zone
}
