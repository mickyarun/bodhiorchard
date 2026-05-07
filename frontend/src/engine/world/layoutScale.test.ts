// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { describe, it, expect, beforeEach } from 'vitest'
import {
  BASELINE_ORCHARD_RADIUS,
  BASELINE_REPO_COUNT,
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

describe('Phase 1 stub: computeLayoutScale ignores repoCount', () => {
  it('returns identical scales for any N (Phase 2 will replace this stub)', () => {
    const a = computeLayoutScale(1)
    const b = computeLayoutScale(50)
    expect(a).toEqual(b)
  })
})

describe('active-scale cache', () => {
  beforeEach(() => resetActiveScale())

  it('lazy-initialises to baseline when never set', () => {
    expect(getActiveScale().orchardRadius).toBe(18)
  })

  it('setActiveScale overrides what subsequent reads see', () => {
    setActiveScale({
      ...computeLayoutScale(BASELINE_REPO_COUNT),
      orchardRadius: 42,
    })
    expect(getActiveScale().orchardRadius).toBe(42)
  })

  it('resetActiveScale clears the cache so the next read lazy-inits', () => {
    setActiveScale({
      ...computeLayoutScale(BASELINE_REPO_COUNT),
      orchardRadius: 42,
    })
    resetActiveScale()
    expect(getActiveScale().orchardRadius).toBe(18)
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

  it('fires the listener during the lazy-init triggered by getActiveScale', () => {
    const seen: number[] = []
    const off = onScaleChange(scale => seen.push(scale.orchardRadius))
    expect(getActiveScale().orchardRadius).toBe(18)
    expect(seen).toEqual([18])
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
