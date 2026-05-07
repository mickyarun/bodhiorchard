// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Orchard radius curve — maps repo count to orchard radius, plus the
 * baseline anchor constants that pin the curve to today's hand-tuned
 * geometry.
 *
 * Lives in its own file so the curve choice is a focused, reviewable
 * artifact: future revisions (linear, piecewise, log, …) land here
 * without touching the broader `LayoutScale` schema.
 *
 * Imported by `shared/world/layoutScale.ts`, which re-exports the
 * baseline constants so today's `import { BASELINE_REPO_COUNT } from
 * './layoutScale'` call sites stay valid.
 */

/** Today's "typical" repo count — the N at which the curve returns
 *  `BASELINE_ORCHARD_RADIUS` and at which all hand-tuned geometry was
 *  authored. Used by the curve floor and as a default at boot. */
export const BASELINE_REPO_COUNT = 8

/** Orchard radius at baseline (N = BASELINE_REPO_COUNT). The geometry
 *  in `shared/world/zones.ts` is back-derived from baseline coords
 *  using this anchor — never edit one without the other. */
export const BASELINE_ORCHARD_RADIUS = 18

/**
 * Hard cap on orchard radius. Past this point the visible world stops
 * growing — the camera frame, perimeter belt, and zone gaps don't have
 * room to keep expanding without breaking the established sense of scale.
 */
export const ORCHARD_RADIUS_MAX = 70

/**
 * Slope: orchard-radius units added per repo above `BASELINE_REPO_COUNT`.
 * 2.5 was tuned against the N=15 visual: prior sqrt curve put trees at
 * ring-1 chord-distance ~9.7u (foliage overlap); slope=2.5 → ring-1
 * chord ~14u (clear separation). Adjust upward for more spread per repo.
 */
const RADIUS_PER_REPO_ABOVE_FLOOR = 2.5

/**
 * Compute orchard radius from repo count via a capped linear curve
 * above the baseline floor:
 *   `R = clamp(BASELINE + RADIUS_PER_REPO_ABOVE_FLOOR * max(N - BASELINE_REPO_COUNT, 0), BASELINE, MAX)`.
 *
 * - Floor at baseline: small orgs (N ≤ BASELINE_REPO_COUNT) get today's
 *   hand-tuned geometry, byte-identical to Phase 1.
 * - Linear growth: each repo above the floor adds ~2.5 units of orchard
 *   radius, with non-hub zones shifting outward by the same Δ (so the
 *   gap from the orchard rim stays constant). Trees on the middle ring
 *   gain enough chord-distance to stop visually overlapping.
 * - Ceiling at MAX: orgs past ~28 repos saturate the world. Tree
 *   placement keeps adding rings inside the orchard, so visual density
 *   continues to scale even after R clamps.
 *
 * Examples:
 *   - N=8  → R=18 (baseline)
 *   - N=15 → R=35.5
 *   - N=20 → R=48
 *   - N=28 → R=68
 *   - N=29+ → R=70 (capped)
 */
export function computeOrchardRadius(repoCount: number): number {
  const above = Math.max(repoCount - BASELINE_REPO_COUNT, 0)
  const r = BASELINE_ORCHARD_RADIUS + RADIUS_PER_REPO_ABOVE_FLOOR * above
  return Math.min(r, ORCHARD_RADIUS_MAX)
}
