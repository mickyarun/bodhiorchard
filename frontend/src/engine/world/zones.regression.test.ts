// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Byte-identical regression test for zone resolution at baseline.
 *
 * Sub-step 1b moved zones from a static `(x,z)` array to a declarative
 * form resolved against `LayoutScale`. This test verifies the refactor
 * preserved exact coordinates: each `getZone(name)` must reproduce its
 * pre-refactor (x,z) to floating-point precision.
 *
 * The expected coords below are the literal values that lived in
 * `shared/world/zones.ts` before 1b. Updating them requires deliberate
 * intent (Phase 2 scaling will).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  ZONE_DECLS,
  buildZones,
  getZone,
  HOUSING_YAW_DEG,
  type ZoneTier,
} from '@shared/world/zones'
import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  resetActiveScale,
  setActiveScale,
} from '@shared/world/layoutScale'

interface ExpectedZone {
  name: string
  tier: ZoneTier
  x: number
  z: number
  radius: number
  yawDeg?: number
}

const EXPECTED: ExpectedZone[] = [
  { name: 'orchard',    tier: 'hub',        x: 0,   z: 0,   radius: 18 },
  { name: 'pavilion',   tier: 'activity',   x: 0,   z: -28, radius: 6 },
  { name: 'coffee_bar', tier: 'activity',   x: -26, z: 10,  radius: 8 },
  { name: 'cafeteria',  tier: 'activity',   x: 26,  z: 10,  radius: 8 },
  { name: 'housing',    tier: 'habitation', x: -44, z: 52,  radius: 14, yawDeg: HOUSING_YAW_DEG },
  { name: 'pool',       tier: 'habitation', x: 30,  z: 40,  radius: 10 },
]

describe('zones byte-identical regression at baseline', () => {
  beforeEach(() => {
    resetActiveScale()
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  })

  for (const expected of EXPECTED) {
    it(`${expected.name} resolves to its pre-refactor (x,z) within 1e-9`, () => {
      const z = getZone(expected.name)
      expect(z).not.toBeNull()
      expect(z!.tier).toBe(expected.tier)
      expect(z!.x).toBeCloseTo(expected.x, 9)
      expect(z!.z).toBeCloseTo(expected.z, 9)
      expect(z!.radius).toBe(expected.radius)
      if (expected.yawDeg !== undefined) {
        expect(z!.yawDeg).toBe(expected.yawDeg)
      } else {
        expect(z!.yawDeg).toBeUndefined()
      }
    })
  }

  it('every declaration corresponds to an EXPECTED entry (no orphan zones)', () => {
    expect(ZONE_DECLS.map(d => d.name).sort()).toEqual(
      EXPECTED.map(e => e.name).sort(),
    )
  })

  it('buildZones(baseline scale) reproduces today’s coords too (parallel path)', () => {
    const baselineScale = computeLayoutScale(BASELINE_REPO_COUNT)
    const built = buildZones(baselineScale)
    expect(built).toHaveLength(EXPECTED.length)
    for (const expected of EXPECTED) {
      const z = built.find(b => b.name === expected.name)!
      expect(z.x).toBeCloseTo(expected.x, 9)
      expect(z.z).toBeCloseTo(expected.z, 9)
    }
  })
})

describe('runtime invariants on resolved zones', () => {
  beforeEach(() => {
    resetActiveScale()
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  })

  it('coffee_bar ↔ housing safety margin holds (≥ 4u, doc invariant from zones.ts:55-59)', () => {
    const cb = getZone('coffee_bar')!
    const h = getZone('housing')!
    const dist = Math.hypot(cb.x - h.x, cb.z - h.z)
    // half-extent at 20 members ≈ 19; coffee_bar.radius = 8.
    // Required clearance = 19 + 8 + safetyMargin(4) = 31.
    const clearance = dist - 19 - 8
    expect(clearance).toBeGreaterThanOrEqual(4)
  })

  it('orchard sits at origin with radius equal to scale.orchardRadius', () => {
    const orchard = getZone('orchard')!
    expect(orchard.x).toBe(0)
    expect(orchard.z).toBe(0)
    expect(orchard.radius).toBe(computeLayoutScale(BASELINE_REPO_COUNT).orchardRadius)
  })
})

describe('zone cache is kept in sync with the active scale (P2-b invalidation hook)', () => {
  // After each scale-mutation test, restore baseline so beforeEach in any
  // sibling describe block sees a consistent starting state.
  afterEach(() => {
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  })

  it('setActiveScale atomically swaps the zone cache so getZone reflects the new orchard radius', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    setActiveScale({ ...baseline, orchardRadius: 30 })
    expect(getZone('orchard')!.radius).toBe(30)
  })

  it('non-hub zones translate outward when the orchard grows (gap preserved)', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    const baselineCoffeeBar = getZone('coffee_bar')!
    const baselineDist = Math.hypot(baselineCoffeeBar.x, baselineCoffeeBar.z)

    setActiveScale({ ...baseline, orchardRadius: 30 }) // +12u from baseline 18

    const grown = getZone('coffee_bar')!
    const grownDist = Math.hypot(grown.x, grown.z)
    // Gap-from-rim is preserved → centre-to-centre grows by exactly the
    // orchard-radius delta (12). Allow 1e-9 for trig round-trip noise.
    expect(grownDist - baselineDist).toBeCloseTo(12, 9)
  })

  it('returning to baseline after a mutation restores the original coords', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    const before = getZone('housing')!
    setActiveScale({ ...baseline, orchardRadius: 42 })
    setActiveScale(baseline)
    const after = getZone('housing')!
    expect(after.x).toBeCloseTo(before.x, 9)
    expect(after.z).toBeCloseTo(before.z, 9)
  })
})
