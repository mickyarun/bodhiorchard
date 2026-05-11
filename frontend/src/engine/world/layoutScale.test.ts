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

import { describe, it, expect, beforeEach } from 'vitest'
import {
  BASELINE_ORCHARD_RADIUS,
  BASELINE_REPO_COUNT,
  DEFAULT_ROOM_KEY,
  computeLayoutScale,
  getActiveScale,
  onScaleChange,
  resetActiveScale,
  setActiveScale,
} from '@shared/world/layoutScale'

describe('computeLayoutScale at baseline reproduces today’s literals', () => {
  const scale = computeLayoutScale(BASELINE_REPO_COUNT)

  it('orchardRadius matches shared/world/zones.ts:62 today', () => {
    expect(scale.orchardRadius).toBe(18)
  })

  it('orchardRadius equals the exported BASELINE_ORCHARD_RADIUS', () => {
    expect(scale.orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
  })

  it('hub geometry matches HubAnchor.ts module constants today', () => {
    expect(scale.hub.plazaRadius).toBe(8.5)
    expect(scale.hub.moundRadius).toBe(4.0)
    expect(scale.hub.moundHeight).toBe(0.7)
    expect(scale.hub.ringRadius).toBe(5.8)
    expect(scale.hub.ringCount).toBe(12)
    expect(scale.hub.treeScale).toBe(3.2)
    expect(scale.hub.plazaExclusionMargin).toBe(0.5)
  })

  it('agentSlot constants match treePositions.ts today', () => {
    expect(scale.agentSlot.treeOffset).toBe(1.8)
    expect(scale.agentSlot.ringStep).toBe(1.2)
    expect(scale.agentSlot.slotsPerRing).toBe(5)
    expect(scale.agentSlot.slotAngleStepRad).toBeCloseTo(
      (40 * Math.PI) / 180,
      12,
    )
  })

  it('perimeter geometry matches today’s HousingState + PineTreeSystem literals', () => {
    expect(scale.perimeter.outerFenceMargin).toBe(8)
    expect(scale.perimeter.pineFramingRadius).toBe(52)
    expect(scale.perimeter.pineRingInner).toBe(55)
    expect(scale.perimeter.pineRingOuter).toBe(85)
  })

  it('treeRingFormula constants match treePositions.ts today', () => {
    expect(scale.treeRingFormula.arcRadiusFactor).toBe(0.65)
    expect(scale.treeRingFormula.arcStartRad).toBeCloseTo(-Math.PI * 0.75, 12)
    expect(scale.treeRingFormula.arcSpanRad).toBeCloseTo(Math.PI * 1.5, 12)
    expect(scale.treeRingFormula.ringsDivisor).toBe(6)
    expect(scale.treeRingFormula.innerRingFactor).toBe(0.3)
    expect(scale.treeRingFormula.outerRingFactor).toBe(0.65)
    expect(scale.treeRingFormula.perRingBase).toBe(6)
    expect(scale.treeRingFormula.perRingGrowth).toBe(2)
    expect(scale.treeRingFormula.ringRotationOffsetRad).toBe(0.5)
  })

  it('moundRadius + fallbackClearance equals today’s FALLBACK_HUB_OFFSET (4.8)', () => {
    // Sub-step 1c drops the FALLBACK_HUB_OFFSET literal in treePositions.ts
    // in favour of this exact sum. Asserting the relationship now locks it
    // before the literal is removed, so 1c can land without surprise drift.
    expect(scale.hub.moundRadius + scale.hub.fallbackClearance).toBeCloseTo(
      4.8,
      12,
    )
  })

  it('fallback offset stays clear of mound + character half-width (~0.4)', () => {
    // Runtime invariant from treePositions.ts:42-47, now executable.
    const fallback = scale.hub.moundRadius + scale.hub.fallbackClearance
    expect(fallback).toBeGreaterThan(scale.hub.moundRadius + 0.4)
  })
})

describe('Phase 2 curve: computeLayoutScale scales orchard with repoCount', () => {
  it('returns baseline at N=BASELINE_REPO_COUNT (byte-identical, no Phase 1 regression)', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(baseline.orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
    expect(baseline.perimeter.pineRingInner).toBe(55)
    expect(baseline.perimeter.pineRingOuter).toBe(85)
    expect(baseline.perimeter.pineFramingRadius).toBe(52)
  })

  it('floors small orgs at the baseline radius (N≤8 → R=18)', () => {
    expect(computeLayoutScale(1).orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
    expect(computeLayoutScale(3).orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
    expect(computeLayoutScale(7).orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
  })

  it('grows linearly above the floor at 2.5u per repo', () => {
    // R = 18 + 2.5 * (N - 8) for 8 ≤ N ≤ where the cap kicks in
    expect(computeLayoutScale(15).orchardRadius).toBeCloseTo(35.5, 9)
    expect(computeLayoutScale(20).orchardRadius).toBeCloseTo(48, 9)
    expect(computeLayoutScale(28).orchardRadius).toBeCloseTo(68, 9)
  })

  it('caps at 70 to bound camera framing and prevent runaway worlds', () => {
    expect(computeLayoutScale(29).orchardRadius).toBe(70)
    expect(computeLayoutScale(200).orchardRadius).toBe(70)
    expect(computeLayoutScale(1000).orchardRadius).toBe(70)
  })

  it('shifts the pine perimeter belt by the same Δ as orchard growth (gap preserved)', () => {
    const big = computeLayoutScale(20)
    const delta = big.orchardRadius - BASELINE_ORCHARD_RADIUS
    expect(big.perimeter.pineRingInner).toBeCloseTo(55 + delta, 9)
    expect(big.perimeter.pineRingOuter).toBeCloseTo(85 + delta, 9)
    expect(big.perimeter.pineFramingRadius).toBeCloseTo(52 + delta, 9)
  })

  it('hub geometry is N-invariant — the central plaza reads at the same human scale', () => {
    const small = computeLayoutScale(3)
    const big = computeLayoutScale(80)
    expect(big.hub).toEqual(small.hub)
  })

  it('curve is monotonically non-decreasing in N', () => {
    const radii = [1, 8, 12, 20, 40, 80, 200].map(n => computeLayoutScale(n).orchardRadius)
    for (let i = 1; i < radii.length; i++) {
      expect(radii[i]).toBeGreaterThanOrEqual(radii[i - 1])
    }
  })
})

describe('active-scale cache', () => {
  beforeEach(() => resetActiveScale())

  it('throws in dev/test when read before any setActiveScale', () => {
    expect(() => getActiveScale()).toThrow(
      /getActiveScale\(\) called before setActiveScale/,
    )
  })

  it('setActiveScale overrides what subsequent reads see', () => {
    setActiveScale({
      ...computeLayoutScale(BASELINE_REPO_COUNT),
      orchardRadius: 42,
    })
    expect(getActiveScale().orchardRadius).toBe(42)
  })

  it('resetActiveScale clears the cache so the next read throws again', () => {
    setActiveScale({
      ...computeLayoutScale(BASELINE_REPO_COUNT),
      orchardRadius: 42,
    })
    resetActiveScale()
    expect(() => getActiveScale()).toThrow()
  })
})

describe('onScaleChange listener hook', () => {
  beforeEach(() => resetActiveScale())

  it('fires the listener when setActiveScale is called', () => {
    const seen: number[] = []
    const off = onScaleChange(scale => seen.push(scale.orchardRadius))
    setActiveScale({
      ...computeLayoutScale(BASELINE_REPO_COUNT),
      orchardRadius: 99,
    })
    expect(seen).toEqual([99])
    off()
  })

  it('does not fire when getActiveScale throws on an unwired default key', () => {
    const seen: number[] = []
    const off = onScaleChange(scale => seen.push(scale.orchardRadius))
    expect(() => getActiveScale()).toThrow()
    expect(seen).toEqual([])
    off()
  })

  it('returns an unsubscribe function that stops further fires', () => {
    const seen: number[] = []
    const off = onScaleChange(scale => seen.push(scale.orchardRadius))
    setActiveScale({ ...computeLayoutScale(BASELINE_REPO_COUNT), orchardRadius: 30 })
    off()
    setActiveScale({ ...computeLayoutScale(BASELINE_REPO_COUNT), orchardRadius: 50 })
    expect(seen).toEqual([30])
  })
})

describe('per-room scale isolation (Phase 2 prerequisite)', () => {
  beforeEach(() => resetActiveScale())

  it('writes under distinct room keys do not clobber each other', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    setActiveScale({ ...baseline, orchardRadius: 21 }, 'org_a')
    setActiveScale({ ...baseline, orchardRadius: 33 }, 'org_b')
    expect(getActiveScale('org_a').orchardRadius).toBe(21)
    expect(getActiveScale('org_b').orchardRadius).toBe(33)
  })

  it('writing under a non-default key leaves the default-key scale untouched', () => {
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT)) // primes default
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    setActiveScale({ ...baseline, orchardRadius: 99 }, 'org_a')
    expect(getActiveScale().orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
    expect(getActiveScale(DEFAULT_ROOM_KEY).orchardRadius).toBe(BASELINE_ORCHARD_RADIUS)
  })

  it('non-default-key writes do NOT fire onScaleChange listeners (Phase 1.5 scope)', () => {
    const seen: number[] = []
    const off = onScaleChange(scale => seen.push(scale.orchardRadius))
    setActiveScale(
      { ...computeLayoutScale(BASELINE_REPO_COUNT), orchardRadius: 99 },
      'org_a',
    )
    expect(seen).toEqual([])
    off()
  })

  it('reading an unwired non-default key throws (no silent baseline fallback)', () => {
    expect(() => getActiveScale('org_unwired')).toThrow(
      /getActiveScale\('org_unwired'\) called before setActiveScale/,
    )
  })

  it('resetActiveScale(roomKey) clears just that key', () => {
    const baseline = computeLayoutScale(BASELINE_REPO_COUNT)
    setActiveScale({ ...baseline, orchardRadius: 21 }, 'org_a')
    setActiveScale({ ...baseline, orchardRadius: 33 }, 'org_b')
    resetActiveScale('org_a')
    expect(() => getActiveScale('org_a')).toThrow()
    expect(getActiveScale('org_b').orchardRadius).toBe(33)
  })
})
