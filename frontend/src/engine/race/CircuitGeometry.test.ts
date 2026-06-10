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
  circuitPose,
  circuitRadiusM,
  laneCenterOffsetM,
} from '@shared/race/CircuitGeometry'
import { LANE_WIDTH_M } from '@shared/race/RaceConstants'

const CIRCUMFERENCE_M = 200
const R = circuitRadiusM(CIRCUMFERENCE_M)

describe('circuitRadiusM', () => {
  it('inverts the circumference formula', () => {
    expect(2 * Math.PI * circuitRadiusM(CIRCUMFERENCE_M)).toBeCloseTo(CIRCUMFERENCE_M, 10)
  })
})

describe('laneCenterOffsetM', () => {
  it('matches the straight track lane-centre formula', () => {
    const laneCount = 4
    const trackWidthM = laneCount * LANE_WIDTH_M
    for (let i = 0; i < laneCount; i++) {
      const straightZ = (i + 0.5) * LANE_WIDTH_M - trackWidthM / 2
      expect(laneCenterOffsetM(i, laneCount)).toBeCloseTo(straightZ, 10)
    }
  })
})

describe('circuitPose', () => {
  it('starts at the world origin heading +X', () => {
    const p = circuitPose(0, CIRCUMFERENCE_M)
    expect(p.x).toBeCloseTo(0, 10)
    expect(p.z).toBeCloseTo(0, 10)
    expect(p.headingRad).toBeCloseTo(0, 10)
  })

  it('lane offsets at the start line equal the straight-track lane Zs', () => {
    const laneCount = 6
    for (let i = 0; i < laneCount; i++) {
      const offset = laneCenterOffsetM(i, laneCount)
      const p = circuitPose(0, CIRCUMFERENCE_M, offset)
      expect(p.x).toBeCloseTo(0, 10)
      expect(p.z).toBeCloseTo(offset, 10)
    }
  })

  it('quarter lap sits beside the centre, heading +Z', () => {
    const p = circuitPose(CIRCUMFERENCE_M / 4, CIRCUMFERENCE_M)
    expect(p.x).toBeCloseTo(R, 8)
    expect(p.z).toBeCloseTo(R, 8)
    expect(p.headingRad).toBeCloseTo(Math.PI / 2, 10)
  })

  it('half lap is diametrically opposite the start, heading -X', () => {
    const p = circuitPose(CIRCUMFERENCE_M / 2, CIRCUMFERENCE_M)
    expect(p.x).toBeCloseTo(0, 8)
    expect(p.z).toBeCloseTo(2 * R, 8)
    expect(p.headingRad).toBeCloseTo(Math.PI, 10)
  })

  it('a full lap returns to the start line', () => {
    const p = circuitPose(CIRCUMFERENCE_M, CIRCUMFERENCE_M)
    expect(p.x).toBeCloseTo(0, 8)
    expect(p.z).toBeCloseTo(0, 8)
    expect(p.headingRad).toBeCloseTo(2 * Math.PI, 10)
  })

  it('heading grows monotonically — no wrap discontinuity for lerp consumers', () => {
    let prev = -1
    for (let arc = 0; arc <= CIRCUMFERENCE_M; arc += 5) {
      const p = circuitPose(arc, CIRCUMFERENCE_M)
      expect(p.headingRad).toBeGreaterThan(prev)
      prev = p.headingRad
    }
  })

  it('an offset lane keeps a constant distance from the circle centre', () => {
    const offset = laneCenterOffsetM(0, 8)
    for (let arc = 0; arc <= CIRCUMFERENCE_M; arc += 13) {
      const p = circuitPose(arc, CIRCUMFERENCE_M, offset)
      const distFromCenter = Math.hypot(p.x - 0, p.z - R)
      expect(distFromCenter).toBeCloseTo(R - offset, 8)
    }
  })
})
