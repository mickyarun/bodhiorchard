// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Regression tests for the HubAnchor geometry contract at baseline.
 *
 * Sub-step 1c moved every layout literal out of HubAnchor.ts into the
 * shared `LayoutScale.hub` block. This test locks today's derived values
 * (exclusion radius, mound collider top, fallback agent offset) so a
 * future scale curve in Phase 2 can't silently regress baseline visuals.
 *
 * The HubAnchor builder needs a real PlayCanvas Application to construct
 * entities — out of scope for a Vitest unit. Instead these tests verify
 * the SAME math the builder runs, against the active scale at baseline.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  resetActiveScale,
  setActiveScale,
} from '@shared/world/layoutScale'
import { getAgentFallbackSlot } from '@shared/world/treePositions'

describe('HubAnchor geometry at baseline', () => {
  beforeEach(() => {
    resetActiveScale()
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  })

  it('plaza exclusion radius equals 9.0 (today’s rim + breathing margin)', () => {
    const { hub } = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(hub.plazaRadius + hub.plazaExclusionMargin).toBeCloseTo(9.0, 12)
  })

  it('mound collider top y equals 0.75 (plaza-to-mound clearance + height)', () => {
    // HubAnchor.build sets `topY = 0.05 + moundHeight`. Lock the value.
    const { hub } = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(0.05 + hub.moundHeight).toBeCloseTo(0.75, 12)
  })

  it('hero tree scale equals 3.2 (today’s HUB_TREE_SCALE)', () => {
    const { hub } = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(hub.treeScale).toBe(3.2)
  })

  it('bush ring count equals 12 (today’s RING_COUNT)', () => {
    const { hub } = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(hub.ringCount).toBe(12)
  })

  it('agent fallback slot sits 4.8u from origin (mound + clearance)', () => {
    // The literal `FALLBACK_HUB_OFFSET = 4.8` was deleted in 1c — this
    // test enforces the derived sum still equals it. With three activity
    // zones at +z-mirror layout the open direction is (0, +1), so the
    // fallback slot lands at (0, +4.8).
    const slot = getAgentFallbackSlot()
    expect(Math.hypot(slot.x, slot.z)).toBeCloseTo(4.8, 9)
  })

  it('fallback offset stays clear of mound + character half-width (~0.4)', () => {
    const { hub } = computeLayoutScale(BASELINE_REPO_COUNT)
    expect(hub.moundRadius + hub.fallbackClearance).toBeGreaterThan(
      hub.moundRadius + 0.4,
    )
  })
})
