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
 * Tests for shared tree + agent placement math.
 *
 * Lives in `frontend/src/` because Vitest's `include` only scans that
 * tree (see vitest.config.ts); the `@shared/*` alias points at the
 * shared/ workspace.
 */

import { describe, it, expect } from 'vitest'
import {
  getAgentSlotAtTree,
  getAgentFallbackSlot,
  getTreePositions,
} from '@shared/world/treePositions'
import { getZone } from '@shared/world/zones'
import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  setActiveScale,
} from '@shared/world/layoutScale'

// Wire baseline before any module-load read of the active-scale cache.
// `getActiveScale()` no longer lazy-inits — production wires this in
// `WorldLayout.ts`, tests must do it explicitly.
setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))

const ORCHARD = getZone('orchard')!

describe('getAgentSlotAtTree', () => {
  it('slot 0 points straight inward at AGENT_TREE_OFFSET from tree', () => {
    const tree = { x: 10, z: 0 }
    const slot = getAgentSlotAtTree(tree, 0)
    // Inward radial from tree toward orchard center (0,0) is -x direction.
    expect(slot.x).toBeCloseTo(tree.x - 1.8, 5)
    expect(slot.z).toBeCloseTo(0, 5)
  })

  it('slots 1 and 2 fan symmetrically around slot 0', () => {
    const tree = { x: 10, z: 0 }
    const s1 = getAgentSlotAtTree(tree, 1)
    const s2 = getAgentSlotAtTree(tree, 2)
    // Mirror across the tree→hub axis (z = 0 here).
    expect(s1.x).toBeCloseTo(s2.x, 5)
    expect(s1.z).toBeCloseTo(-s2.z, 5)
    // Both sit at the same radius from the tree as slot 0.
    const r1 = Math.hypot(s1.x - tree.x, s1.z - tree.z)
    const r2 = Math.hypot(s2.x - tree.x, s2.z - tree.z)
    expect(r1).toBeCloseTo(1.8, 5)
    expect(r2).toBeCloseTo(1.8, 5)
  })

  it('slot 5 wraps to ring 1 with larger radius', () => {
    const tree = { x: 10, z: 0 }
    const slot5 = getAgentSlotAtTree(tree, 5)
    const r = Math.hypot(slot5.x - tree.x, slot5.z - tree.z)
    expect(r).toBeCloseTo(1.8 + 1.2, 5)
  })

  it('handles trees off the x-axis — radial still points toward center', () => {
    const tree = { x: 0, z: 10 }
    const slot = getAgentSlotAtTree(tree, 0)
    // Inward radial from (0,10) toward (0,0) is -z direction.
    expect(slot.x).toBeCloseTo(0, 5)
    expect(slot.z).toBeCloseTo(tree.z - 1.8, 5)
  })

  it('throws when tree coincides with orchard center', () => {
    expect(() => getAgentSlotAtTree({ x: ORCHARD.x, z: ORCHARD.z }, 0)).toThrow(
      /coincide/,
    )
  })
})

describe('getAgentFallbackSlot', () => {
  it('sits near the bodhi tree at a small hub-offset distance', () => {
    const slot = getAgentFallbackSlot()
    const dist = Math.hypot(slot.x - ORCHARD.x, slot.z - ORCHARD.z)
    // Small offset — well inside the orchard radius, not on the grass.
    expect(dist).toBeLessThan(ORCHARD.radius)
    expect(dist).toBeGreaterThan(0)
  })

  it('points away from activity-zone centroid', () => {
    // Activity zones: pavilion (0,-28), coffee_bar (-26,10), cafeteria (26,10)
    // Centroid ≈ (0, -2.67); fallback points to roughly +z (opposite).
    const slot = getAgentFallbackSlot()
    expect(slot.z - ORCHARD.z).toBeGreaterThan(0)
  })
})

describe('getTreePositions', () => {
  it('returns the requested count', () => {
    expect(getTreePositions(0)).toHaveLength(0)
    expect(getTreePositions(3)).toHaveLength(3)
    expect(getTreePositions(12)).toHaveLength(12)
  })

  it('places all trees inside the orchard zone', () => {
    const trees = getTreePositions(8)
    for (const t of trees) {
      const dist = Math.hypot(t.x - ORCHARD.x, t.z - ORCHARD.z)
      expect(dist).toBeLessThanOrEqual(ORCHARD.radius)
    }
  })
})
