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
  ALLOWED_DISTANCES_M,
  LOOP_LENGTH_M,
  lapLabel,
  lapCountToDistanceM,
  distanceMToLapCount,
} from '@shared/race/RaceConstants'

describe('lap helpers', () => {
  it('round-trips lap count and distance through the loop length', () => {
    for (const laps of [1, 2]) {
      expect(distanceMToLapCount(lapCountToDistanceM(laps))).toBe(laps)
    }
    expect(lapCountToDistanceM(1)).toBe(LOOP_LENGTH_M)
  })

  it('labels singular vs plural laps correctly', () => {
    expect(lapLabel(100)).toBe('1 lap')
    expect(lapLabel(200)).toBe('2 laps')
  })

  it('produces a non-empty label for every allowed race distance', () => {
    for (const d of ALLOWED_DISTANCES_M) {
      expect(lapLabel(d)).toMatch(/^\d+ laps?$/)
    }
  })
})
