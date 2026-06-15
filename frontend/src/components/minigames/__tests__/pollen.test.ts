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
  MOTE_EMOJI,
  isMoteAlive,
  motePositionAt,
  spawnMote,
} from '@shared/minigames/pollen'

describe('spawnMote', () => {
  it('spawns within the arena with a valid emoji index', () => {
    const m = spawnMote(1, 1000, () => 0.5)
    expect(m.id).toBe(1)
    expect(m.spawnAtMs).toBe(1000)
    expect(m.x).toBeGreaterThanOrEqual(8)
    expect(m.x).toBeLessThanOrEqual(92)
    expect(m.vy).toBeGreaterThan(0) // always rises
    expect(m.emojiIndex).toBeGreaterThanOrEqual(0)
    expect(m.emojiIndex).toBeLessThan(MOTE_EMOJI.length)
  })
})

describe('motePositionAt', () => {
  const mote = spawnMote(1, 1000, () => 0.5) // x=50, vy=14, vx=0

  it('is at the spawn point at spawn time and rises over time', () => {
    expect(motePositionAt(mote, 1000)).toEqual({ x: 50, y: 104 })
    expect(motePositionAt(mote, 2000).y).toBeCloseTo(90, 6) // 104 - 14
  })

  it('is deterministic (the server can replay any mote position)', () => {
    expect(motePositionAt(mote, 3456)).toEqual(motePositionAt(mote, 3456))
  })

  it('drifts horizontally when vx is non-zero', () => {
    const drifting = spawnMote(2, 0, () => 0.75) // vx = 1.5
    expect(motePositionAt(drifting, 1000).x).toBeCloseTo(drifting.x + 1.5, 6)
  })
})

describe('isMoteAlive', () => {
  const mote = spawnMote(1, 1000, () => 0.5) // vy=14 → reaches y=-8 at +8s

  it('is alive while on-screen and dead once it drifts off the top', () => {
    expect(isMoteAlive(mote, 1000)).toBe(true) // just spawned
    expect(isMoteAlive(mote, 7000)).toBe(true) // y = 104 - 14*6 = 20
    expect(isMoteAlive(mote, 9000)).toBe(false) // y = 104 - 14*8 = -8 (off-screen)
  })
})
