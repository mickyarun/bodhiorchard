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
  makeRacer,
  setMoving,
  tick,
  triggerSprintTap,
  type Racer,
} from '@shared/race/RacePhysics'
import {
  boostPadPositionsM,
  hurdlePositionsM,
  isBoosted,
  isStumbling,
  triggerJump,
} from '@shared/race/RaceTrackFeatures'
import {
  BOOST_PAD_FRACTIONS,
  BOOST_TARGET_MPS,
  BOOST_DURATION_MS,
  HURDLE_FRACTIONS,
  HURDLE_JUMP_WINDOW_MS,
  HURDLE_JUMP_COOLDOWN_MS,
  HURDLE_STUMBLE_MS,
  RUN_TARGET_MPS,
  WALK_TARGET_MPS,
  STAMINA_INITIAL,
  TICK_MS,
} from '@shared/race/RaceConstants'

const TRACK_M = 100

/** Advance `count` server ticks starting after `fromMs`; returns the last nowMs. */
function advance(r: Racer, fromMs: number, count: number): number {
  let now = fromMs
  for (let i = 0; i < count; i++) {
    now += TICK_MS
    tick([r], TICK_MS, now, TRACK_M)
  }
  return now
}

describe('feature positions', () => {
  it('boost pads sit at the configured fractions of the distance', () => {
    expect(boostPadPositionsM(TRACK_M)).toEqual(BOOST_PAD_FRACTIONS.map((f) => f * TRACK_M))
    expect(boostPadPositionsM(200)).toEqual(BOOST_PAD_FRACTIONS.map((f) => f * 200))
  })

  it('hurdles sit at the configured fractions of the distance', () => {
    expect(hurdlePositionsM(TRACK_M)).toEqual(HURDLE_FRACTIONS.map((f) => f * TRACK_M))
    expect(hurdlePositionsM(200)).toEqual(HURDLE_FRACTIONS.map((f) => f * 200))
  })
})

describe('boost pads', () => {
  it('crossing a pad opens a boost window', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    r.positionM = boostPadPositionsM(TRACK_M)[0] - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.boostUntilMs).toBe(TICK_MS + BOOST_DURATION_MS)
    expect(isBoosted(r, TICK_MS)).toBe(true)
  })

  it('boosted velocity climbs past the sprint target without sprint taps', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    r.positionM = boostPadPositionsM(TRACK_M)[0] - 0.01
    const crossedAt = TICK_MS
    tick([r], TICK_MS, crossedAt, TRACK_M)
    advance(r, crossedAt, 12) // 600ms of boost — enough to accelerate 3 → 9
    expect(r.velocityMps).toBeGreaterThan(RUN_TARGET_MPS)
    expect(r.velocityMps).toBeLessThanOrEqual(BOOST_TARGET_MPS)
  })

  it('boost does not drain stamina', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    r.positionM = boostPadPositionsM(TRACK_M)[0] - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    advance(r, TICK_MS, 10)
    expect(r.staminaPct).toBeGreaterThanOrEqual(STAMINA_INITIAL)
  })

  it('each pad fires at most once per racer', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    const padM = boostPadPositionsM(TRACK_M)[0]
    r.positionM = padM - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.boostPadsHit).toBe(1)

    // Force a hypothetical re-cross — the bitmask must hold the latch.
    const expiredMs = TICK_MS + BOOST_DURATION_MS + TICK_MS
    r.boostUntilMs = 0
    r.positionM = padM - 0.01
    tick([r], TICK_MS, expiredMs, TRACK_M)
    expect(r.boostUntilMs).toBe(0)
    expect(r.boostPadsHit).toBe(1)
  })

  it('crossing the finish line on the same tick skips feature processing', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = RUN_TARGET_MPS
    r.positionM = TRACK_M - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.finished).toBe(true)
    expect(r.boostPadsHit).toBe(0)
  })
})

describe('hurdles', () => {
  function racerJustBeforeHurdle(): Racer {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = RUN_TARGET_MPS
    r.positionM = hurdlePositionsM(TRACK_M)[0] - 0.01
    return r
  }

  it('clipping a hurdle cuts velocity and opens a stumble window', () => {
    const r = racerJustBeforeHurdle()
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.velocityMps).toBeLessThan(RUN_TARGET_MPS / 2 + 0.5)
    expect(isStumbling(r, TICK_MS)).toBe(true)
    expect(r.stumbleUntilMs).toBe(TICK_MS + HURDLE_STUMBLE_MS)
  })

  it('clipping forfeits a banked sprint window', () => {
    const r = racerJustBeforeHurdle()
    triggerSprintTap(r, 0)
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.sprintUntilMs).toBeLessThanOrEqual(TICK_MS)
  })

  it('stumbling caps speed at walk even with fresh sprint taps', () => {
    const r = racerJustBeforeHurdle()
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    triggerSprintTap(r, TICK_MS)
    advance(r, TICK_MS, 4) // still inside HURDLE_STUMBLE_MS
    expect(r.velocityMps).toBeLessThanOrEqual(WALK_TARGET_MPS)
  })

  it('sprint speed is reachable again once the stumble expires', () => {
    const r = racerJustBeforeHurdle()
    let now = TICK_MS
    tick([r], TICK_MS, now, TRACK_M)
    now = advance(r, now, Math.ceil(HURDLE_STUMBLE_MS / TICK_MS))
    for (let i = 0; i < 10; i++) {
      triggerSprintTap(r, now)
      now = advance(r, now, 1)
    }
    expect(r.velocityMps).toBeGreaterThan(WALK_TARGET_MPS)
  })

  it('an active jump window clears the hurdle without penalty', () => {
    const r = racerJustBeforeHurdle()
    triggerJump(r, 0)
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(isStumbling(r, TICK_MS)).toBe(false)
    expect(r.velocityMps).toBeGreaterThan(WALK_TARGET_MPS)
  })
})

describe('triggerJump', () => {
  it('opens the airborne window for HURDLE_JUMP_WINDOW_MS', () => {
    const r = makeRacer('a')
    triggerJump(r, 0)
    expect(r.jumpUntilMs).toBe(HURDLE_JUMP_WINDOW_MS)
  })

  it('honours the very first tap at nowMs = 0', () => {
    const r = makeRacer('a')
    triggerJump(r, 0)
    expect(r.jumpUntilMs).toBeGreaterThan(0)
  })

  it('ignores taps inside the cooldown', () => {
    const r = makeRacer('a')
    triggerJump(r, 0)
    triggerJump(r, HURDLE_JUMP_COOLDOWN_MS - 1)
    expect(r.jumpUntilMs).toBe(HURDLE_JUMP_WINDOW_MS)
  })

  it('accepts a tap once the cooldown has elapsed', () => {
    const r = makeRacer('a')
    triggerJump(r, 0)
    triggerJump(r, HURDLE_JUMP_COOLDOWN_MS)
    expect(r.jumpUntilMs).toBe(HURDLE_JUMP_COOLDOWN_MS + HURDLE_JUMP_WINDOW_MS)
  })

  it('is a no-op for finished racers', () => {
    const r = makeRacer('a')
    r.finished = true
    triggerJump(r, 0)
    expect(r.jumpUntilMs).toBe(0)
  })
})
