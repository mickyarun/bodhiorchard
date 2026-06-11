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

import { describe, it, expect } from 'vitest'
import { loopPose, loopBounds } from '@shared/race/LoopPath'
import { circuitPose, laneCenterOffsetM } from '@shared/race/CircuitGeometry'
import {
  ALLOWED_DISTANCES_M,
  LANE_WIDTH_M,
  MAX_RACERS,
} from '@shared/race/RaceConstants'

const CIRCUMFERENCE_M = 200

/**
 * Below this curvature radius, a lane offset along the inward normal
 * self-intersects on the widest allowed track. Half the 10-lane track
 * width plus a 1 m safety margin.
 */
const MIN_SAFE_CURVATURE_RADIUS_M = (MAX_RACERS * LANE_WIDTH_M) / 2 + 1

/** Numeric arc step for curvature / closure sweeps. */
const SWEEP_STEP_M = 0.25

describe('loopPose anchoring + conventions', () => {
  it('starts at the world origin heading +X (parity with circuitPose)', () => {
    const loop = loopPose(0, CIRCUMFERENCE_M)
    const circle = circuitPose(0, CIRCUMFERENCE_M)
    expect(loop.x).toBeCloseTo(circle.x, 8)
    expect(loop.z).toBeCloseTo(circle.z, 8)
    expect(loop.headingRad).toBeCloseTo(circle.headingRad, 8)
  })

  it('lane offsets at the start line equal the straight-track lane Zs', () => {
    const laneCount = 8
    for (let i = 0; i < laneCount; i++) {
      const offset = laneCenterOffsetM(i, laneCount)
      const loop = loopPose(0, CIRCUMFERENCE_M, offset)
      const circle = circuitPose(0, CIRCUMFERENCE_M, offset)
      expect(loop.x).toBeCloseTo(circle.x, 8)
      expect(loop.z).toBeCloseTo(circle.z, 8)
      expect(loop.z).toBeCloseTo(offset, 8)
    }
  })

  it('closes: pose(L) returns to pose(0) with heading 2π', () => {
    const start = loopPose(0, CIRCUMFERENCE_M)
    const end = loopPose(CIRCUMFERENCE_M, CIRCUMFERENCE_M)
    expect(end.x).toBeCloseTo(start.x, 6)
    expect(end.z).toBeCloseTo(start.z, 6)
    expect(end.headingRad).toBeCloseTo(start.headingRad + 2 * Math.PI, 6)
  })

  it('heading grows monotonically — safe to lerp without unwrapping', () => {
    let prev = -1
    for (let arc = 0; arc <= CIRCUMFERENCE_M; arc += 1) {
      const h = loopPose(arc, CIRCUMFERENCE_M).headingRad
      expect(h).toBeGreaterThan(prev)
      prev = h
    }
  })
})

describe('loopPose arc-length scaling', () => {
  it.each([...ALLOWED_DISTANCES_M])(
    'total sampled path length equals the %im circumference exactly',
    (c) => {
      let total = 0
      let prev = loopPose(0, c)
      for (let arc = SWEEP_STEP_M; arc <= c + 1e-9; arc += SWEEP_STEP_M) {
        const p = loopPose(arc, c)
        total += Math.hypot(p.x - prev.x, p.z - prev.z)
        prev = p
      }
      // Chord sum of a smooth curve slightly underestimates arc length;
      // at 0.25 m steps the defect is < 0.01% — assert within 0.05%.
      expect(Math.abs(total - c) / c).toBeLessThan(5e-4)
    },
  )
})

describe('loop curvature safety', () => {
  it.each([...ALLOWED_DISTANCES_M])(
    'minimum curvature radius at %im exceeds the widest-lane bound',
    (c) => {
      // Circumradius of consecutive centreline triplets — a direct
      // numeric measurement, independent of the harmonic derivation.
      let minRadius = Infinity
      for (let arc = SWEEP_STEP_M; arc + SWEEP_STEP_M <= c; arc += SWEEP_STEP_M) {
        const a = loopPose(arc - SWEEP_STEP_M, c)
        const b = loopPose(arc, c)
        const d = loopPose(arc + SWEEP_STEP_M, c)
        const ab = Math.hypot(a.x - b.x, a.z - b.z)
        const bd = Math.hypot(b.x - d.x, b.z - d.z)
        const ad = Math.hypot(a.x - d.x, a.z - d.z)
        const area = Math.abs((b.x - a.x) * (d.z - a.z) - (d.x - a.x) * (b.z - a.z)) / 2
        if (area < 1e-9) continue
        const r = (ab * bd * ad) / (4 * area)
        if (r < minRadius) minRadius = r
      }
      expect(minRadius).toBeGreaterThan(MIN_SAFE_CURVATURE_RADIUS_M)
    },
  )

  it('the deepest inward lane edge always advances forward (no cusps)', () => {
    // When curvature radius drops below the lateral offset, the offset
    // curve develops a cusp and momentarily travels backwards — the
    // visual "lane folds over itself" failure. Verify the widest track's
    // innermost edge always moves along the local travel direction.
    const offset = (MAX_RACERS * LANE_WIDTH_M) / 2
    let prev = loopPose(0, CIRCUMFERENCE_M, offset)
    for (let arc = SWEEP_STEP_M; arc <= CIRCUMFERENCE_M; arc += SWEEP_STEP_M) {
      const lane = loopPose(arc, CIRCUMFERENCE_M, offset)
      const heading = loopPose(arc, CIRCUMFERENCE_M).headingRad
      const forward = (lane.x - prev.x) * Math.cos(heading) + (lane.z - prev.z) * Math.sin(heading)
      expect(forward).toBeGreaterThan(0)
      prev = lane
    }
  })
})

describe('loop is visibly non-circular', () => {
  it('radial variation about the centroid is at least 8%', () => {
    let cx = 0
    let cz = 0
    const samples: Array<{ x: number; z: number }> = []
    for (let arc = 0; arc < CIRCUMFERENCE_M; arc += SWEEP_STEP_M) {
      const p = loopPose(arc, CIRCUMFERENCE_M)
      samples.push(p)
      cx += p.x
      cz += p.z
    }
    cx /= samples.length
    cz /= samples.length
    let min = Infinity
    let max = 0
    let sum = 0
    for (const p of samples) {
      const r = Math.hypot(p.x - cx, p.z - cz)
      min = Math.min(min, r)
      max = Math.max(max, r)
      sum += r
    }
    expect((max - min) / (sum / samples.length)).toBeGreaterThan(0.08)
  })
})

describe('loopBounds', () => {
  it('bounds every centreline pose and nothing degenerate', () => {
    const b = loopBounds(CIRCUMFERENCE_M)
    expect(b.maxX).toBeGreaterThan(b.minX)
    expect(b.maxZ).toBeGreaterThan(b.minZ)
    for (let arc = 0; arc <= CIRCUMFERENCE_M; arc += 1) {
      const p = loopPose(arc, CIRCUMFERENCE_M)
      expect(p.x).toBeGreaterThanOrEqual(b.minX - 1e-6)
      expect(p.x).toBeLessThanOrEqual(b.maxX + 1e-6)
      expect(p.z).toBeGreaterThanOrEqual(b.minZ - 1e-6)
      expect(p.z).toBeLessThanOrEqual(b.maxZ + 1e-6)
    }
    // The anchored start sits on the path, so the origin is inside the box.
    expect(b.minX).toBeLessThanOrEqual(0)
    expect(b.maxX).toBeGreaterThanOrEqual(0)
    // Span sanity: same order of magnitude as the circle's diameter.
    const circleDiameter = CIRCUMFERENCE_M / Math.PI
    expect(b.maxX - b.minX).toBeGreaterThan(circleDiameter * 0.7)
    expect(b.maxX - b.minX).toBeLessThan(circleDiameter * 1.4)
  })
})
