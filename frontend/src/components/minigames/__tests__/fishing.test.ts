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
  randomPhase,
  randomSweepRate,
  randomZoneStart,
  scoreForHook,
  sweepRateForCast,
} from '@shared/minigames/fishing'

describe('bobberPositionAt', () => {
  it('is centred at elapsed 0 with phase 0, and deterministic in its params', () => {
    expect(bobberPositionAt(0, 1, 0)).toBeCloseTo(0.5, 6)
    // Same (elapsed, rate, phase) always gives the same position (server replays it).
    expect(bobberPositionAt(123, 1.2, 0.4)).toBe(bobberPositionAt(123, 1.2, 0.4))
  })

  it('opens at a phase-shifted point, not always the centre', () => {
    // A non-zero phase moves the start away from 0.5 — that's the per-play variety.
    expect(bobberPositionAt(0, 1, 0.5)).not.toBeCloseTo(0.5, 3)
  })

  it('stays within [0, 1] across rates and phases', () => {
    for (const rate of [0.8, 1.2, 1.6, 2.2]) {
      for (const ph of [0, 0.5, 1, 1.5]) {
        for (let ms = 0; ms <= 4000; ms += 50) {
          const p = bobberPositionAt(ms, rate, ph)
          expect(p).toBeGreaterThanOrEqual(0)
          expect(p).toBeLessThanOrEqual(1)
        }
      }
    }
  })

  it('later casts sweep faster (base rate)', () => {
    expect(sweepRateForCast(4)).toBeGreaterThan(sweepRateForCast(0))
  })
})

describe('randomSweepRate', () => {
  it('jitters around the per-cast base and is always positive', () => {
    const base = sweepRateForCast(2)
    expect(randomSweepRate(2, () => 0)).toBeCloseTo(base * 0.85, 6) // slow extreme
    expect(randomSweepRate(2, () => 1)).toBeCloseTo(base * 1.35, 6) // fast extreme
    expect(randomSweepRate(2, () => 0.5)).toBeCloseTo(base * 1.1, 6)
    expect(randomSweepRate(0, () => 0)).toBeGreaterThan(0)
  })
})

describe('randomPhase', () => {
  it('spans a full sine period (0..2)', () => {
    expect(randomPhase(() => 0)).toBe(0)
    expect(randomPhase(() => 0.5)).toBe(1)
    expect(randomPhase(() => 0.999)).toBeLessThan(2)
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
