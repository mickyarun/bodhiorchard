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
  GAME_MS,
  MOTE_EMOJI,
  SPAWN_JITTER,
  SPAWN_MIN_MS,
  SPAWN_START_MS,
  isMoteAlive,
  jitteredIntervalMs,
  motePositionAt,
  spawnIntervalMs,
  spawnMote,
} from '@shared/minigames/pollen'

describe('spawnMote', () => {
  it('spawns within the arena with a valid emoji index', () => {
    const m = spawnMote(1, 1000, () => 0.5)
    expect(m.id).toBe(1)
    expect(m.spawnAtMs).toBe(1000)
    expect(m.x).toBeGreaterThanOrEqual(6)
    expect(m.x).toBeLessThanOrEqual(94)
    expect(m.vy).toBeGreaterThan(0) // always rises
    expect(m.emojiIndex).toBeGreaterThanOrEqual(0)
    expect(m.emojiIndex).toBeLessThan(MOTE_EMOJI.length)
  })

  it('rises faster the later in the round it spawns', () => {
    const early = spawnMote(1, 0, () => 0.5, 0)
    const late = spawnMote(1, 0, () => 0.5, GAME_MS)
    expect(late.vy).toBeGreaterThan(early.vy)
  })
})

describe('spawnIntervalMs', () => {
  it('ramps from the start interval down to the floor', () => {
    expect(spawnIntervalMs(0)).toBe(SPAWN_START_MS)
    expect(spawnIntervalMs(GAME_MS)).toBe(SPAWN_MIN_MS)
    expect(spawnIntervalMs(GAME_MS / 2)).toBeLessThan(SPAWN_START_MS)
    expect(spawnIntervalMs(GAME_MS / 2)).toBeGreaterThan(SPAWN_MIN_MS)
  })
})

describe('jitteredIntervalMs', () => {
  it('is neutral at rng=0.5 (returns the base cadence)', () => {
    expect(jitteredIntervalMs(0, () => 0.5)).toBeCloseTo(spawnIntervalMs(0), 6)
    expect(jitteredIntervalMs(GAME_MS, () => 0.5)).toBeCloseTo(spawnIntervalMs(GAME_MS), 6)
  })

  it('stays within ±SPAWN_JITTER of the base cadence at the extremes', () => {
    const base = spawnIntervalMs(GAME_MS / 2)
    expect(jitteredIntervalMs(GAME_MS / 2, () => 0)).toBeCloseTo(base * (1 - SPAWN_JITTER), 6)
    expect(jitteredIntervalMs(GAME_MS / 2, () => 1)).toBeCloseTo(base * (1 + SPAWN_JITTER), 6)
  })
})

describe('motePositionAt', () => {
  const mote = spawnMote(1, 1000, () => 0.5) // x=50, vx=0

  it('is at the spawn point at spawn time and rises over time', () => {
    expect(motePositionAt(mote, 1000)).toEqual({ x: 50, y: 104 })
    expect(motePositionAt(mote, 2000).y).toBeCloseTo(104 - mote.vy, 6) // one second up
  })

  it('is deterministic (the server can replay any mote position)', () => {
    expect(motePositionAt(mote, 3456)).toEqual(motePositionAt(mote, 3456))
  })

  it('drifts horizontally when vx is non-zero', () => {
    const drifting = spawnMote(2, 0, () => 0.75) // vx > 0
    expect(motePositionAt(drifting, 1000).x).toBeCloseTo(drifting.x + drifting.vx, 6)
  })
})

describe('isMoteAlive', () => {
  const mote = spawnMote(1, 1000, () => 0.5)

  it('is alive while on-screen and dead once it drifts off the top', () => {
    expect(isMoteAlive(mote, 1000)).toBe(true) // just spawned at y=104
    expect(isMoteAlive(mote, 2000)).toBe(true) // risen one step, still on-screen
    // Far enough out that even the slowest mote has left the top.
    expect(isMoteAlive(mote, 1000 + 20_000)).toBe(false)
  })
})
