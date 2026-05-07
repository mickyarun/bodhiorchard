// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * LayoutScale — single source of truth for every world-geometry constant.
 *
 * Frontend (`frontend/src/engine/world/`) and multiplayer
 * (`multiplayer/src/sim/`) read from here via `getActiveScale()`. Both
 * processes call `setActiveScale(computeLayoutScale(repoCount))` at boot.
 * A lazy fallback to baseline keeps any read-before-boot path safe.
 *
 * Hard rule: layout literals never live in frontend or multiplayer source.
 * If a number drives geometry, it goes in this file (or a sibling
 * `shared/world/*.ts` that also reads from `getActiveScale()`).
 *
 * Phase 1: `computeLayoutScale` ignores `repoCount` and returns baseline
 * values regardless of N — this is a pure refactor, no behaviour change.
 * Phase 2 will swap the stub for an N-driven curve.
 */

const RAD_PER_DEG = Math.PI / 180

/** Hub-anchor geometry (the central plaza + mound + bush ring + hero tree). */
export interface HubGeometry {
  /** Outer cobble disc — hero-scale to hold canopy shadow. */
  plazaRadius: number
  /** Raised earth pad under the hero tree. */
  moundRadius: number
  /** Visible elevation of the mound. */
  moundHeight: number
  /** Bush/flower ring sits between mound and plaza edge. */
  ringRadius: number
  /** Number of bushes around the ring (chosen for ringRadius circumference). */
  ringCount: number
  /** Uniform scale-up applied to the hub bodhi tree. */
  treeScale: number
  /** Extra exclusion radius added to plazaRadius so paths stop with breathing margin. */
  plazaExclusionMargin: number
  /** Clearance added to moundRadius for the agent fallback slot. Must exceed character half-width (~0.4). */
  fallbackClearance: number
}

/** Agent placement geometry — where agents stand relative to a tree. */
export interface AgentSlotGeometry {
  /** Base radial distance from a tree at which an agent stands. */
  treeOffset: number
  /** Additional radial step per full ring when stacking. */
  ringStep: number
  /** Slots around the hub-facing hemisphere before pushing to the next ring. */
  slotsPerRing: number
  /** Angular step between adjacent slots on an arc, in radians. */
  slotAngleStepRad: number
}

/** Perimeter geometry — the fence ring + pine forest belt that frame the
 *  habitable world. All values absolute today; Phase 2 may parameterise
 *  them by `orchardRadius` so the perimeter pushes outward as the world
 *  grows. */
export interface PerimeterGeometry {
  /** Distance past `max(getWorldRadius, housingOuterReach)` where the
   *  outer rail-fence ring sits. Used by both the visual fence builder
   *  and the Rapier perimeter collider so the two stay in lockstep. */
  outerFenceMargin: number
  /** Radius of the pine framing-clump centres. Sits between activity ring
   *  and habitation zones to frame sightlines. */
  pineFramingRadius: number
  /** Inner edge of the perimeter pine belt — closer to the world centre. */
  pineRingInner: number
  /** Outer edge of the perimeter pine belt — past which only sky shows. */
  pineRingOuter: number
}

/** Tree-position formulas. The ≤8 branch lays trees on a single arc;
 *  the >8 branch packs them into concentric rings. See `treePositions.ts`. */
export interface TreeRingFormula {
  /** ≤8: arc radius = orchardRadius * arcRadiusFactor. */
  arcRadiusFactor: number
  /** ≤8: arc start angle (rad). e.g. -3π/4 = 270° arc opening +z. */
  arcStartRad: number
  /** ≤8: arc total span (rad). e.g. 3π/2 = 270°. */
  arcSpanRad: number
  /** >8: rings = ceil(count / ringsDivisor). */
  ringsDivisor: number
  /** >8: innermost ring at orchardRadius * innerRingFactor. */
  innerRingFactor: number
  /** >8: outermost ring extra factor above innerRingFactor. */
  outerRingFactor: number
  /** >8: ring 0 holds perRingBase trees; each subsequent ring grows by perRingGrowth. */
  perRingBase: number
  perRingGrowth: number
  /** >8: per-ring angular offset (rad) so trees on adjacent rings don't align radially. */
  ringRotationOffsetRad: number
}

export interface LayoutScale {
  /** Orchard hub-zone radius. Phase 1 returns baseline regardless of N. */
  orchardRadius: number
  hub: HubGeometry
  agentSlot: AgentSlotGeometry
  treeRingFormula: TreeRingFormula
  /** Perimeter geometry — fence ring + pine forest belt. */
  perimeter: PerimeterGeometry
}

// Note: Phase 2's tier-wide zone-distance scaling will likely add
// `tierGap: Record<ZoneTier, number>` (or a strategy fn) here. Earlier
// drafts had `activityGap`/`habitationGap` placeholder fields; cut per
// the type-design review — speculative `0`-typed fields create a false
// impression of capability and add noise for every reader.

/** Today's "typical" repo count — the baseline at which all literals were tuned. */
export const BASELINE_REPO_COUNT = 8

/** Orchard radius at baseline. Re-exported so `shared/world/zones.ts` can
 *  back-derive polar form from baseline coords without redeclaring. */
export const BASELINE_ORCHARD_RADIUS = 18

/**
 * Compute the layout scale for a given repo count.
 *
 * Phase 1 implementation: returns baseline values regardless of N. Phase 2
 * will replace this stub with an N-driven curve.
 */
export function computeLayoutScale(_repoCount: number): LayoutScale {
  return {
    orchardRadius: BASELINE_ORCHARD_RADIUS,
    hub: {
      plazaRadius: 8.5,
      moundRadius: 4.0,
      moundHeight: 0.7,
      ringRadius: 5.8,
      ringCount: 12,
      treeScale: 3.2,
      plazaExclusionMargin: 0.5,
      // moundRadius (4.0) + fallbackClearance (0.8) = 4.8 = today's
      // FALLBACK_HUB_OFFSET in shared/world/treePositions.ts. Sub-step 1c
      // drops that literal in favour of this derivation.
      fallbackClearance: 0.8,
    },
    agentSlot: {
      treeOffset: 1.8,
      ringStep: 1.2,
      slotsPerRing: 5,
      slotAngleStepRad: 40 * RAD_PER_DEG,
    },
    treeRingFormula: {
      arcRadiusFactor: 0.65,
      arcStartRad: -Math.PI * 0.75,
      arcSpanRad: Math.PI * 1.5,
      ringsDivisor: 6,
      innerRingFactor: 0.3,
      outerRingFactor: 0.65,
      perRingBase: 6,
      perRingGrowth: 2,
      ringRotationOffsetRad: 0.5,
    },
    perimeter: {
      outerFenceMargin: 8,
      pineFramingRadius: 52,
      pineRingInner: 55,
      pineRingOuter: 85,
    },
  }
}

// Cache + derived helpers live in `layoutScaleCache.ts` to keep this
// "schema + factory" file under the size cap. Re-exported here so every
// consumer can import from a single path.
export {
  computeOuterPerimeterRadius,
  getActiveScale,
  onScaleChange,
  resetActiveScale,
  setActiveScale,
} from './layoutScaleCache'
