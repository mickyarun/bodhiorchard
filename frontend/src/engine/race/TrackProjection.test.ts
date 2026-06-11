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
import {
  StraightProjection,
  CircuitProjection,
  entityYawDeg,
} from './TrackProjection'
import { laneCenterOffsetM } from '@shared/race/CircuitGeometry'
import { loopPose } from '@shared/race/LoopPath'
import { LANE_WIDTH_M } from '@shared/race/RaceConstants'

const CIRCUMFERENCE_M = 200

describe('StraightProjection', () => {
  it('reproduces the original placement math: arc = X, lateral = Z, heading 0', () => {
    const proj = new StraightProjection()
    // Same numbers the pre-projection code wrote directly: avatars at
    // (positionM, laneZ), pads at (padX, 0), hurdle posts at (x, ±postZ).
    for (const [arc, lateral] of [
      [0, 0],
      [42.5, 0],
      [100, -2.25],
      [73.2, 2.25],
    ]) {
      const p = proj.pose(arc, lateral)
      expect(p.x).toBe(arc)
      expect(p.z).toBe(lateral)
      expect(p.headingDeg).toBe(0)
    }
  })

  it('lane offsets equal the straight-track lane-centre Z formula', () => {
    const proj = new StraightProjection()
    const laneCount = 4
    const trackWidthM = laneCount * LANE_WIDTH_M
    for (let i = 0; i < laneCount; i++) {
      const straightZ = (i + 0.5) * LANE_WIDTH_M - trackWidthM / 2
      expect(proj.pose(0, laneCenterOffsetM(i, laneCount)).z).toBeCloseTo(straightZ, 10)
    }
  })
})

describe('CircuitProjection', () => {
  it('matches loopPose, with heading converted to degrees', () => {
    const proj = new CircuitProjection(CIRCUMFERENCE_M)
    for (const arc of [0, 13, CIRCUMFERENCE_M / 4, CIRCUMFERENCE_M / 2, CIRCUMFERENCE_M]) {
      for (const lateral of [0, laneCenterOffsetM(0, 6), laneCenterOffsetM(5, 6)]) {
        const expected = loopPose(arc, CIRCUMFERENCE_M, lateral)
        const p = proj.pose(arc, lateral)
        expect(p.x).toBeCloseTo(expected.x, 10)
        expect(p.z).toBeCloseTo(expected.z, 10)
        expect(p.headingDeg).toBeCloseTo((expected.headingRad * 180) / Math.PI, 10)
      }
    }
  })

  it('shares the start line with the straight projection (lane parity)', () => {
    const circuit = new CircuitProjection(CIRCUMFERENCE_M)
    const straight = new StraightProjection()
    for (let i = 0; i < 8; i++) {
      const offset = laneCenterOffsetM(i, 8)
      const c = circuit.pose(0, offset)
      const s = straight.pose(0, offset)
      expect(c.x).toBeCloseTo(s.x, 10)
      expect(c.z).toBeCloseTo(s.z, 10)
      expect(c.headingDeg).toBeCloseTo(s.headingDeg, 10)
    }
  })

  it('heading grows monotonically in degrees — safe to lerp across laps', () => {
    const proj = new CircuitProjection(CIRCUMFERENCE_M)
    let prev = -1
    for (let arc = 0; arc <= CIRCUMFERENCE_M; arc += 7) {
      const h = proj.pose(arc, 0).headingDeg
      expect(h).toBeGreaterThan(prev)
      prev = h
    }
    expect(proj.pose(CIRCUMFERENCE_M, 0).headingDeg).toBeCloseTo(360, 8)
  })
})

describe('entityYawDeg', () => {
  it('negates the heading (PlayCanvas +Y rotation turns +X toward -Z)', () => {
    // toBeCloseTo: heading 0 negates to -0, which Object.is distinguishes
    // from +0 — irrelevant for a rotation angle.
    expect(entityYawDeg(0)).toBeCloseTo(0, 12)
    expect(entityYawDeg(90)).toBe(-90)
    expect(entityYawDeg(360)).toBe(-360)
  })
})
