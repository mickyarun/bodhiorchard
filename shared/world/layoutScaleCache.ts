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
 * the resolved zone array exposed by `getZones()` in `shared/world/zones.ts`)
 * in sync via atomic reassignment.
 *
 * **Per-room storage** — the cache is keyed by an arbitrary `roomKey`
 * string so multiplayer's many `OrgRoom` instances can hold distinct
 * scales without trampling each other (see `OrgRoom` notes in Phase 2).
 * Calls that omit the key target `DEFAULT_ROOM_KEY` — the path used by
 * the frontend (single-process, single-scale) and by every today-shipped
 * multiplayer call site. Non-default keys are write-only storage in
 * Phase 1.5: reads still go through the default key, and `onScaleChange`
 * only fires on default-key writes. Phase 2 wires per-room reads via a
 * future `withRoomKey` context helper, at which point the zone cache and
 * listener fan-out become per-key as well.
 *
 * Re-exported from `shared/world/layoutScale.ts` so consumers can import
 * everything from one path.
 */

import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  type LayoutScale,
} from './layoutScale'

/**
 * Storage key used by every today-shipped call site. Frontend (one process,
 * one scale) and multiplayer's module-load boot wire (one process, one
 * shared baseline) both target this key.
 */
export const DEFAULT_ROOM_KEY = '__default__'

const scalesByRoom = new Map<string, LayoutScale>()

type ScaleChangeListener = (scale: LayoutScale) => void
const scaleChangeListeners = new Set<ScaleChangeListener>()

/**
 * Subscribe to default-key scale changes. The listener fires every time
 * the default scale is installed — including the lazy init triggered by
 * the first `getActiveScale()` call before any explicit boot wire fires.
 *
 * Returns an unsubscribe function.
 *
 * Used by `shared/world/zones.ts` to rebuild its eagerly-resolved
 * resolved zone cache. Listeners MUST NOT call `setActiveScale`
 * themselves (would re-emit and recurse).
 *
 * Non-default room keys do NOT fire listeners today — those are
 * write-only storage until Phase 2 wires per-room reads.
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
 * because the zone-cache rebuild listener registered in `zones.ts` is
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
 * Boot-time: install the active scale for `roomKey` (default key when
 * omitted). Subsequent reads of the same key see this value.
 *
 * For default-key writes, registered `onScaleChange` listeners fire
 * after the cache is updated. Non-default-key writes are silent — Phase
 * 2 will introduce a `withRoomKey` context helper that swaps the active
 * key and fires listeners on switch.
 *
 * Re-entrancy is forbidden — listeners must NOT call `setActiveScale`.
 * The runtime guard below converts that contract from docstring-only
 * into a loud throw, replacing what would otherwise be a stack-overflow
 * crash at unrelated code with a pinpoint error.
 */
export function setActiveScale(
  scale: LayoutScale,
  roomKey: string = DEFAULT_ROOM_KEY,
): void {
  if (emittingScaleChange) {
    throw new Error(
      '[layoutScaleCache] setActiveScale called re-entrantly from an ' +
      'onScaleChange listener — listeners must be pure (see docstring).',
    )
  }
  scalesByRoom.set(roomKey, scale)
  if (roomKey !== DEFAULT_ROOM_KEY) return
  emittingScaleChange = true
  try {
    emitScaleChange(scale)
  } finally {
    emittingScaleChange = false
  }
}

/**
 * Read the active scale for `roomKey` (default key when omitted).
 *
 * The default-key path lazy-initialises to baseline on first read,
 * which also fires `onScaleChange` listeners — so any module registered
 * before the first read still receives the initial value.
 *
 * Non-default keys do NOT lazy-init; an unknown key throws so callers
 * can't silently render baseline geometry when their per-room boot
 * wire failed to run. (Phase 2 introduces this read path.)
 */
export function getActiveScale(roomKey: string = DEFAULT_ROOM_KEY): LayoutScale {
  const cached = scalesByRoom.get(roomKey)
  if (cached) return cached
  if (roomKey === DEFAULT_ROOM_KEY) {
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
    return scalesByRoom.get(DEFAULT_ROOM_KEY)!
  }
  throw new Error(
    `[layoutScaleCache] getActiveScale('${roomKey}') called before ` +
    `setActiveScale for that key — Phase 2 callers must wire the ` +
    `per-room scale on room create.`,
  )
}

/**
 * Test-only: clear cached scale(s).
 * - With no argument, clears every key (whole-process reset).
 * - With a key, clears that key only.
 *
 * After a default-key reset the next `getActiveScale()` re-runs the
 * lazy baseline init and re-fires listeners, simulating a fresh process.
 */
export function resetActiveScale(roomKey?: string): void {
  if (roomKey === undefined) {
    scalesByRoom.clear()
    return
  }
  scalesByRoom.delete(roomKey)
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
