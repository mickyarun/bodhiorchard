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
 * Byte-identical regression test for the tree-position algorithm at baseline.
 *
 * The hardcode-bag cleanup (sub-step 1a) moved every numeric constant out of
 * `shared/world/treePositions.ts` into `shared/world/layoutScale.ts`. This
 * test verifies the refactor preserved exact behaviour: the public
 * `getTreePositions(count)` must produce coordinates byte-identical (within
 * 1e-9) to the pre-refactor algorithm at the baseline repo count.
 *
 * The "expected" reference inlines the original formula with the original
 * literal constants. If a future change updates either the formula or the
 * literals, this test forces a deliberate update — which is exactly what we
 * want when Phase 2 swaps the scale curve.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { getTreePositions } from '@shared/world/treePositions'
import {
  BASELINE_REPO_COUNT,
  computeLayoutScale,
  resetActiveScale,
  setActiveScale,
} from '@shared/world/layoutScale'

const ORCHARD_X = 0
const ORCHARD_Z = 0
const ORCHARD_RADIUS = 18

function expectedTreePositions(count: number): Array<{ x: number; z: number }> {
  const positions: Array<{ x: number; z: number }> = []
  if (count <= 8) {
    const arcRadius = ORCHARD_RADIUS * 0.65
    for (let i = 0; i < count; i++) {
      const angle =
        (i / Math.max(count - 1, 1)) * Math.PI * 1.5 - Math.PI * 0.75
      positions.push({
        x: ORCHARD_X + Math.cos(angle) * arcRadius,
        z: ORCHARD_Z + Math.sin(angle) * arcRadius,
      })
    }
  } else {
    const rings = Math.ceil(count / 6)
    let placed = 0
    for (let ring = 0; ring < rings && placed < count; ring++) {
      const ringRadius =
        ORCHARD_RADIUS * 0.3 + (ring * ORCHARD_RADIUS * 0.65) / rings
      const perRing = Math.min(6 + ring * 2, count - placed)
      for (let i = 0; i < perRing && placed < count; i++) {
        const angle = (i / perRing) * Math.PI * 2 + ring * 0.5
        positions.push({
          x: ORCHARD_X + Math.cos(angle) * ringRadius,
          z: ORCHARD_Z + Math.sin(angle) * ringRadius,
        })
        placed++
      }
    }
  }
  return positions
}

describe('getTreePositions byte-identical regression at baseline', () => {
  beforeEach(() => {
    resetActiveScale()
    setActiveScale(computeLayoutScale(BASELINE_REPO_COUNT))
  })

  for (const n of [1, 4, 8, 9, 12, 30] as const) {
    it(`count=${n} matches the pre-refactor algorithm to 1e-9`, () => {
      const actual = getTreePositions(n)
      const expected = expectedTreePositions(n)
      expect(actual).toHaveLength(expected.length)
      for (let i = 0; i < expected.length; i++) {
        expect(actual[i].x).toBeCloseTo(expected[i].x, 9)
        expect(actual[i].z).toBeCloseTo(expected[i].z, 9)
      }
    })
  }

  it('count=0 produces no positions', () => {
    expect(getTreePositions(0)).toEqual([])
  })
})
