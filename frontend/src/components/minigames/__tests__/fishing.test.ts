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

import { describe, expect, it } from 'vitest'
import {
  FISHING_MAX_SCORE,
  ZONE_WIDTH,
  bobberPositionAt,
  randomZoneStart,
  scoreForHook,
  sweepRateForCast,
} from '@shared/minigames/fishing'

describe('bobberPositionAt', () => {
  it('starts at the centre (0.5) and is deterministic', () => {
    expect(bobberPositionAt(0, 0)).toBeCloseTo(0.5, 6)
    // Same elapsed + cast always gives the same position (server can replay it).
    expect(bobberPositionAt(123, 2)).toBe(bobberPositionAt(123, 2))
  })

  it('stays within [0, 1]', () => {
    for (let cast = 0; cast < 5; cast++) {
      for (let ms = 0; ms <= 4000; ms += 50) {
        const p = bobberPositionAt(ms, cast)
        expect(p).toBeGreaterThanOrEqual(0)
        expect(p).toBeLessThanOrEqual(1)
      }
    }
  })

  it('later casts sweep faster', () => {
    expect(sweepRateForCast(4)).toBeGreaterThan(sweepRateForCast(0))
  })
})

describe('scoreForHook', () => {
  // Zone centred at 0.5 → centre = 0.5, half-width = ZONE_WIDTH/2 = 0.08.
  const zoneStart = 0.5 - ZONE_WIDTH / 2

  it('awards 10 for a bullseye at the zone centre', () => {
    expect(scoreForHook(0.5, zoneStart)).toBe(10)
  })

  it('awards the mid/edge bands by distance from centre', () => {
    expect(scoreForHook(0.5 + 0.04, zoneStart)).toBe(7) // offset 0.5 → mid
    expect(scoreForHook(0.5 + 0.07, zoneStart)).toBe(4) // offset 0.875 → edge
  })

  it('awards 0 for a hook outside the zone', () => {
    expect(scoreForHook(0.5 + ZONE_WIDTH, zoneStart)).toBe(0)
    expect(scoreForHook(0.0, zoneStart)).toBe(0)
  })
})

describe('randomZoneStart', () => {
  it('keeps the whole zone on the water for any rng value', () => {
    for (const r of [0, 0.25, 0.5, 0.75, 0.999]) {
      const start = randomZoneStart(() => r)
      expect(start).toBeGreaterThanOrEqual(0)
      expect(start + ZONE_WIDTH).toBeLessThanOrEqual(1)
    }
  })
})

describe('FISHING_MAX_SCORE', () => {
  it('is five perfect casts', () => {
    expect(FISHING_MAX_SCORE).toBe(50)
  })
})
