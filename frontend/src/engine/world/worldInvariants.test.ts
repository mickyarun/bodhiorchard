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
 * Layout invariants of the shared world across org sizes. The frontend engine
 * and the multiplayer server both read `shared/world`, so these must hold for
 * every repo count, not only the baseline the regression tests pin.
 */
import { afterAll, describe, expect, it } from 'vitest'
import {
  BASELINE_ORCHARD_RADIUS,
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  resetActiveScale,
  setActiveScale,
} from '@shared/world/layoutScale'
import { ZONE_DECLS, buildZones, getZones, requireZone, type Zone } from '@shared/world/zones'
import { buildRoutes, evalRouteAt } from '@shared/world/paths'
import { getTreePositions } from '@shared/world/treePositions'
import { ORCHARD_RADIUS_MAX } from '@shared/world/orchardCurve'

const REPO_COUNTS = [0, 1, 2, 7, 8, 9, 12, 15, 20, 28, 29, 40, 100]
const EPS = 1e-9

function useScale(repoCount: number): void {
  setActiveScale(computeLayoutScale(repoCount))
}

function gapFromRim(zone: Zone, orchardRadius: number): number {
  return Math.hypot(zone.x, zone.z) - orchardRadius - zone.radius
}

afterAll(() => {
  resetActiveScale()
  setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
})

describe('zones across repo counts', () => {
  it('declares unique zone names and exactly one hub', () => {
    const names = ZONE_DECLS.map(d => d.name)
    expect(new Set(names).size).toBe(names.length)
    expect(ZONE_DECLS.filter(d => d.tier === 'hub')).toHaveLength(1)
  })

  it.each(REPO_COUNTS)('no two zones overlap at %i repos', (n) => {
    const zones = buildZones(computeLayoutScale(n))
    for (let i = 0; i < zones.length; i++) {
      for (let j = i + 1; j < zones.length; j++) {
        const a = zones[i]!
        const b = zones[j]!
        const dist = Math.hypot(a.x - b.x, a.z - b.z)
        expect(dist, `${a.name} vs ${b.name}`).toBeGreaterThanOrEqual(a.radius + b.radius)
      }
    }
  })

  it.each(REPO_COUNTS)('keeps each zone gap and bearing from the orchard at %i repos', (n) => {
    const base = buildZones(computeLayoutScale(BASELINE_REPO_COUNT))
    const scale = computeLayoutScale(n)
    const zones = buildZones(scale)
    zones.forEach((zone, i) => {
      const ref = base[i]!
      if (zone.tier === 'hub') {
        expect(zone).toMatchObject({ x: 0, z: 0, radius: scale.orchardRadius })
        return
      }
      const baselineGap = gapFromRim(ref, BASELINE_ORCHARD_RADIUS)
      expect(gapFromRim(zone, scale.orchardRadius)).toBeCloseTo(baselineGap, 9)
      expect(Math.atan2(zone.z, zone.x)).toBeCloseTo(Math.atan2(ref.z, ref.x), 9)
      expect(zone.radius).toBe(ref.radius)
    })
  })

  it('never grows the orchard past its cap', () => {
    for (const n of [...REPO_COUNTS, 10_000]) {
      expect(computeLayoutScale(n).orchardRadius).toBeLessThanOrEqual(ORCHARD_RADIUS_MAX)
    }
  })

  it('is deterministic for the same repo count', () => {
    expect(computeLayoutScale(17)).toEqual(computeLayoutScale(17))
    expect(buildZones(computeLayoutScale(17))).toEqual(buildZones(computeLayoutScale(17)))
  })

  it('swaps the live zone cache when the active scale changes', () => {
    useScale(40)
    expect(requireZone('orchard').radius).toBe(computeLayoutScale(40).orchardRadius)
    useScale(BASELINE_REPO_COUNT)
    expect(requireZone('orchard').radius).toBe(BASELINE_ORCHARD_RADIUS)
  })

  it('names the missing zone when a required zone is absent', () => {
    expect(() => requireZone('volcano')).toThrow(/requireZone\('volcano'\)/)
  })
})

describe('paths across repo counts', () => {
  it.each(REPO_COUNTS)('connects the hub to every other zone at %i repos', (n) => {
    useScale(n)
    const zones = getZones()
    const nonHub = zones.filter(z => z.tier !== 'hub')
    const routes = buildRoutes(zones)
    expect(routes).toHaveLength(nonHub.length)
    routes.forEach((route, i) => {
      const zone = nonHub[i]!
      expect(evalRouteAt(route, 0)).toEqual({ x: 0, z: 0 })
      const end = evalRouteAt(route, 1)
      expect(end.x).toBeCloseTo(zone.x, 9)
      expect(end.z).toBeCloseTo(zone.z, 9)
      expect(route.kind).toBe(zone.tier === 'activity' ? 'primary' : 'secondary')
    })
  })

  it('samples straight routes monotonically from hub to zone', () => {
    useScale(BASELINE_REPO_COUNT)
    for (const route of buildRoutes(getZones())) {
      let last = -1
      for (let t = 0; t <= 1 + EPS; t += 0.1) {
        const p = evalRouteAt(route, Math.min(t, 1))
        const d = Math.hypot(p.x, p.z)
        expect(d).toBeGreaterThanOrEqual(last)
        last = d
      }
    }
  })
})

describe('repo trees across repo counts', () => {
  it.each(REPO_COUNTS)('places %i trees inside the orchard without stacking', (n) => {
    useScale(n)
    const orchard = requireZone('orchard')
    const trees = getTreePositions(n)
    expect(trees).toHaveLength(n)
    for (const t of trees) {
      expect(Math.hypot(t.x - orchard.x, t.z - orchard.z)).toBeLessThan(orchard.radius)
    }
    for (let i = 0; i < trees.length; i++) {
      for (let j = i + 1; j < trees.length; j++) {
        const d = Math.hypot(trees[i]!.x - trees[j]!.x, trees[i]!.z - trees[j]!.z)
        expect(d, `trees ${i} and ${j}`).toBeGreaterThan(1)
      }
    }
  })

  it('returns identical coordinates for the same count (server and client agree)', () => {
    useScale(23)
    expect(getTreePositions(23)).toEqual(getTreePositions(23))
  })
})
