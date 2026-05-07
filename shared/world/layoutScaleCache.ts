// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Active-scale cache + derived geometry helpers.
 *
 * Frontend and multiplayer read the live layout via `getActiveScale()`.
 * At boot each process calls `setActiveScale(computeLayoutScale(repoCount))`.
 * A lazy fallback to baseline keeps any read-before-boot path safe.
 *
 * Listeners registered via `onScaleChange` keep dependent caches (e.g.
 * `shared/world/zones.ts`'s eagerly-resolved `ZONES`) in sync.
 *
 * Re-exported from `shared/world/layoutScale.ts` so consumers can import
 * everything from one path.
 */

import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  type LayoutScale,
} from './layoutScale'

let activeScale: LayoutScale | null = null

type ScaleChangeListener = (scale: LayoutScale) => void
const scaleChangeListeners = new Set<ScaleChangeListener>()

/**
 * Subscribe to scale changes. The listener fires every time the active
 * scale is installed — including the lazy init triggered by the first
 * `getActiveScale()` call before any explicit boot wire fires.
 *
 * Returns an unsubscribe function.
 *
 * Used by `shared/world/zones.ts` to rebuild its eagerly-resolved
 * `ZONES` array when Phase 2's N-driven curve flows through. Listeners
 * MUST NOT call `setActiveScale` themselves (would re-emit and recurse).
 */
export function onScaleChange(listener: ScaleChangeListener): () => void {
  scaleChangeListeners.add(listener)
  return () => {
    scaleChangeListeners.delete(listener)
  }
}

/**
 * Fire every listener with the new scale. Each listener runs in its own
 * try/catch so a single bad listener can't abort the cascade — critical
 * because the `ZONES` rebuild listener registered in `zones.ts` is
 * load-bearing for every consumer of `getZone()`.
 */
function emitScaleChange(scale: LayoutScale): void {
  for (const listener of scaleChangeListeners) {
    try {
      listener(scale)
    } catch (err) {
      console.error(
        '[layoutScaleCache] onScaleChange listener threw — continuing cascade:',
        err,
      )
    }
  }
}

let emittingScaleChange = false

/**
 * Boot-time: install the active scale. Subsequent reads see this value;
 * registered `onScaleChange` listeners fire after the cache is updated.
 *
 * Re-entrancy is forbidden — listeners must NOT call `setActiveScale`.
 * The runtime guard below converts that contract from docstring-only
 * into a loud throw, replacing what would otherwise be a stack-overflow
 * crash at unrelated code with a pinpoint error.
 *
 * TODO(Phase2): one Node process hosts many `OrgRoom` instances. When
 * Phase 2 starts calling this per-room with non-baseline scales, room A's
 * call will clobber the cache that room B reads from — tree positions
 * leak across orgs. Before Phase 2 wires real `repoCount` per room, swap
 * this module-global for a per-room context (e.g. `Map<roomId, LayoutScale>`)
 * or pass `LayoutScale` explicitly through the call chain.
 */
export function setActiveScale(scale: LayoutScale): void {
  if (emittingScaleChange) {
    throw new Error(
      '[layoutScaleCache] setActiveScale called re-entrantly from an ' +
      'onScaleChange listener — listeners must be pure (see docstring).',
    )
  }
  activeScale = scale
  emittingScaleChange = true
  try {
    emitScaleChange(scale)
  } finally {
    emittingScaleChange = false
  }
}

/**
 * Read the active scale. Lazy-initialises to baseline on first read,
 * which also fires `onScaleChange` listeners — so any module registered
 * before the first read still receives the initial value.
 */
export function getActiveScale(): LayoutScale {
  if (!activeScale) setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  return activeScale!
}

/** Test-only: clear the cache so a test can simulate a fresh process. */
export function resetActiveScale(): void {
  activeScale = null
}

// ─── Derived geometry helpers ────────────────────────────────────────────────
// Formulas that combine `LayoutScale` with caller-supplied dynamic values
// (e.g. a runtime-computed village reach) live here so the geometry math
// stays in `shared/world/` even when its inputs come from frontend builders.

/**
 * Outer perimeter radius for the rail fence + Rapier collider. Takes the
 * larger of the static zone-derived world radius and the dynamic village
 * outer reach so the rail grows to enclose housing when member count
 * pushes its footprint past the static `housing` zone radius. Margin
 * comes from `LayoutScale.perimeter.outerFenceMargin`.
 *
 * Used by `frontend/src/engine/buildings/HousingState.getOuterPerimeterRadius`.
 */
export function computeOuterPerimeterRadius(
  staticWorldRadius: number,
  villageOuterReach: number,
): number {
  return (
    Math.max(staticWorldRadius, villageOuterReach) +
    getActiveScale().perimeter.outerFenceMargin
  )
}
