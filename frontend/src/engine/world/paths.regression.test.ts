// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Regression tests for path-route generation at baseline.
 *
 * Sub-step 1d moved `END_TRIM`, `evalRouteAt`, route declarations, and
 * `buildRoutes` from `frontend/.../PathSystem.ts` to
 * `shared/world/paths.ts`. This test asserts the move preserved exact
 * behaviour: routes generated from baseline zones must have the same
 * `from`, `to`, and `kind` as before, and `evalRouteAt` math is intact.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import {
  END_TRIM,
  buildRoutes,
  evalRouteAt,
  type PathRoute,
} from '@shared/world/paths'
import { buildZones } from '@shared/world/zones'
import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  resetActiveScale,
} from '@shared/world/layoutScale'

describe('END_TRIM constant', () => {
  it('equals 0.08 (today’s value)', () => {
    expect(END_TRIM).toBe(0.08)
  })
})

describe('buildRoutes at baseline reproduces today’s routes', () => {
  beforeEach(() => resetActiveScale())

  const zones = buildZones(computeLayoutScale(BASELINE_REPO_COUNT))
  const routes = buildRoutes(zones)

  it('emits one route per non-hub zone (5 routes for today’s 6 zones)', () => {
    expect(routes).toHaveLength(zones.filter(z => z.tier !== 'hub').length)
    expect(routes).toHaveLength(5)
  })

  it('every route starts at the orchard hub (0, 0)', () => {
    for (const r of routes) {
      expect(r.fromX).toBe(0)
      expect(r.fromZ).toBe(0)
    }
  })

  it('routes zip 1:1 with non-hub zones, in declaration order', () => {
    // Stronger than coord-matching: zip non-hub zones against routes by
    // index. Catches axis swaps, kind swaps, and dropped/reordered zones
    // that a coord-lookup test would silently accept.
    const nonHubZones = zones.filter(z => z.tier !== 'hub')
    expect(routes).toHaveLength(nonHubZones.length)
    for (let i = 0; i < routes.length; i++) {
      const r = routes[i]
      const z = nonHubZones[i]
      expect(r.toX).toBe(z.x)
      expect(r.toZ).toBe(z.z)
      const expectedKind = z.tier === 'activity' ? 'primary' : 'secondary'
      expect(r.kind).toBe(expectedKind)
    }
  })

  it('all routes are straight (today’s baseline has no Bezier paths)', () => {
    for (const r of routes) {
      expect(r.curve).toBe('straight')
    }
  })

  it('throws when no hub zone is present (loud-fail invariant)', () => {
    const noHub = zones.filter(z => z.tier !== 'hub')
    expect(() => buildRoutes(noHub)).toThrow(/no 'hub' zone/)
  })
})

describe('evalRouteAt math', () => {
  it('linearly interpolates straight routes', () => {
    const route: PathRoute = { curve: 'straight', fromX: 0, fromZ: 0, toX: 10, toZ: 6 }
    expect(evalRouteAt(route, 0)).toEqual({ x: 0, z: 0 })
    expect(evalRouteAt(route, 1)).toEqual({ x: 10, z: 6 })
    const mid = evalRouteAt(route, 0.5)
    expect(mid.x).toBe(5)
    expect(mid.z).toBe(3)
  })

  it('computes the quadratic Bezier midpoint for curved routes', () => {
    const route: PathRoute = {
      curve: 'bezier',
      fromX: 0, fromZ: 0,
      toX: 10, toZ: 0,
      controlX: 5, controlZ: 8,
    }
    const mid = evalRouteAt(route, 0.5)
    // Quadratic Bezier at t=0.5 = 0.25*from + 0.5*control + 0.25*to.
    expect(mid.x).toBeCloseTo(5, 12)
    expect(mid.z).toBeCloseTo(4, 12) // 0.25*0 + 0.5*8 + 0.25*0
  })
})
