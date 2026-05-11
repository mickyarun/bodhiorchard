// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Path geometry — routes connecting world zones, plus the constants that
 * pin path sampling. Single source of truth consumed by:
 *   - `frontend/src/engine/world/PathSystem.ts` — renders the strips
 *   - `frontend/src/engine/world/GrassDressing.ts` — wear-halo overlays
 *   - `frontend/src/engine/world/DecorativePropScatter.ts` — propscatter
 *   - any future system that samples routes (LanternSystem, etc.)
 *
 * Routes are derived from the zone array rather than hand-listed so
 * adding a zone automatically gets a route. Caller passes the zones so
 * special-cases (e.g. routing to a village gate instead of its geometric
 * centre) can substitute coordinates without forking the algorithm.
 *
 * Per the world-layout invariant, NO frontend or multiplayer file owns
 * path geometry — this file is the home.
 */

import type { Zone } from './zones'

export type PathKind = 'primary' | 'secondary'

interface PathRouteBase {
  fromX: number
  fromZ: number
  toX: number
  toZ: number
  /** Visual tier. Defaults to 'primary' for backward compatibility. */
  kind?: PathKind
}

export interface StraightRoute extends PathRouteBase {
  curve: 'straight'
}

export interface BezierRoute extends PathRouteBase {
  curve: 'bezier'
  controlX: number
  controlZ: number
}

/**
 * Discriminated by `curve` so straight + curved routes can't be silently
 * mixed: a `BezierRoute` always has both control coords; a `StraightRoute`
 * has neither. Eliminates the prior `controlX?/controlZ?` partial-state
 * class where one-but-not-the-other was a valid type but a meaningless
 * runtime.
 */
export type PathRoute = StraightRoute | BezierRoute

/** Fraction of route length trimmed at each end so paths stop shy of zone
 *  discs rather than poking into them. Shared by any system that samples
 *  routes (GrassDressing, DecorativePropScatter, LanternSystem). */
export const END_TRIM = 0.08

/**
 * Evaluate a route position at parameter t ∈ [0,1].
 * Exposed so other systems (e.g. LanternSystem) walking the same routes
 * follow curves consistently with rendered paths.
 */
export function evalRouteAt(route: PathRoute, t: number): { x: number; z: number } {
  if (route.curve === 'straight') {
    return {
      x: route.fromX + (route.toX - route.fromX) * t,
      z: route.fromZ + (route.toZ - route.fromZ) * t,
    }
  }
  const mt = 1 - t
  return {
    x: mt * mt * route.fromX + 2 * mt * t * route.controlX + t * t * route.toX,
    z: mt * mt * route.fromZ + 2 * mt * t * route.controlZ + t * t * route.toZ,
  }
}

/**
 * Build routes from a tiered zone layout — straight paths radiating from
 * the hub. Activity zones become 'primary' routes (sand + stones);
 * habitation zones become 'secondary' (dirt, no stones).
 *
 * An earlier design curved primary paths and routed secondary through
 * activity for visual branching, but both caused path-through-wall
 * misalignment with the radial fence gates (gates face the hub per the
 * fence builder). The primary/secondary hierarchy now reads purely from
 * width + material.
 *
 * Caller passes the zone array so special-case positions (e.g. routing to
 * a village's gate position rather than its geometric centre) can be
 * substituted without forking the algorithm.
 */
export function buildRoutes(zones: ReadonlyArray<Zone>): PathRoute[] {
  const hub = zones.find(z => z.tier === 'hub')
  if (!hub) {
    // Loud fail rather than silent empty-array — a missing hub means
    // every downstream system (paths, grass-wear, lanterns, prop-scatter
    // path-avoidance) silently produces nothing and the user sees a
    // "weird-looking but plausible" garden with no diagnostic. The
    // orchard hub is a hard invariant of this codebase — match the
    // `requireOrchard` precedent in `treePositions.ts`.
    throw new Error(
      "[paths] buildRoutes called with no 'hub' zone — at least one " +
      "zone with tier='hub' is required (see shared/world/zones.ts).",
    )
  }
  const routes: PathRoute[] = []
  for (const zone of zones) {
    if (zone.tier === 'hub') continue
    routes.push({
      curve: 'straight',
      fromX: hub.x, fromZ: hub.z,
      toX: zone.x, toZ: zone.z,
      kind: zone.tier === 'activity' ? 'primary' : 'secondary',
    })
  }
  return routes
}
