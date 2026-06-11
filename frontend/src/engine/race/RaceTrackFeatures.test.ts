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
  isKnockedDown,
  triggerJump,
} from '@shared/race/RaceTrackFeatures'
import {
  BOOST_PAD_FRACTIONS,
  BOOST_TARGET_MPS,
  BOOST_DURATION_MS,
  HURDLE_FRACTIONS,
  HURDLE_JUMP_WINDOW_MS,
  HURDLE_JUMP_COOLDOWN_MS,
  HURDLE_KNOCKDOWN_MS,
  LOOP_LENGTH_M,
  RUN_TARGET_MPS,
  WALK_TARGET_MPS,
  STAMINA_INITIAL,
  TICK_MS,
} from '@shared/race/RaceConstants'

// One physical loop; a 1-lap race finishes at LOOP_LENGTH_M.
const TRACK_M = LOOP_LENGTH_M
// A 2-lap race over the same loop — the finish line is twice the loop.
const TWO_LAP_M = 2 * LOOP_LENGTH_M

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
  it('boost pads sit at the configured fractions of the loop length', () => {
    expect(boostPadPositionsM()).toEqual(BOOST_PAD_FRACTIONS.map((f) => f * LOOP_LENGTH_M))
    expect(boostPadPositionsM(LOOP_LENGTH_M)).toEqual(
      BOOST_PAD_FRACTIONS.map((f) => f * LOOP_LENGTH_M),
    )
  })

  it('hurdles sit at the configured fractions of the loop length', () => {
    expect(hurdlePositionsM()).toEqual(HURDLE_FRACTIONS.map((f) => f * LOOP_LENGTH_M))
    expect(hurdlePositionsM(LOOP_LENGTH_M)).toEqual(
      HURDLE_FRACTIONS.map((f) => f * LOOP_LENGTH_M),
    )
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

  it('a pad fires at most once within a single lap (position is monotonic)', () => {
    // Step across the first pad once; the boost window opens and, since
    // position never goes backwards within a lap, no second fire occurs.
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    const padM = boostPadPositionsM()[0]
    r.positionM = padM - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.boostUntilMs).toBe(TICK_MS + BOOST_DURATION_MS)

    // A later tick that does NOT re-cross the pad must not re-fire it.
    const laterMs = TICK_MS + BOOST_DURATION_MS + TICK_MS
    r.boostUntilMs = 0
    tick([r], TICK_MS, laterMs, TRACK_M) // advances forward, past the pad
    expect(r.boostUntilMs).toBe(0)
  })

  it('crossing the finish line on the same tick skips feature processing', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = RUN_TARGET_MPS
    r.positionM = TRACK_M - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.finished).toBe(true)
    expect(r.boostUntilMs).toBe(0)
  })
})

// Per-lap firing on the single physical loop: a 1-lap race fires each
// feature once (parity with the pre-lap behaviour); a 2-lap race fires
// each feature twice — once per lap — and the start-line wrap is handled.
describe('per-lap loop-space feature firing', () => {
  /**
   * Drive a racer at a steady speed from the start to `untilM`, counting
   * how many distinct ticks open a fresh boost window (pad fires) and how
   * many ticks open a knockdown (hurdle fires). Jumps are never triggered
   * so every hurdle crossing knocks the racer down.
   */
  function countFeatureFires(
    finishM: number,
    untilM: number,
  ): { padFires: number; hurdleFires: number } {
    const r = makeRacer('a')
    setMoving(r, true)
    let now = 0
    let padFires = 0
    let hurdleFires = 0
    let prevBoostUntil = r.boostUntilMs
    let prevKnockUntil = r.knockdownUntilMs
    // Walk the whole way (isMoving held, no sprint taps); after a hurdle
    // knockdown the racer re-accelerates from rest on its own — it still
    // crosses every downstream feature, just later.
    while (r.positionM < untilM && !r.finished && now < 400_000) {
      now += TICK_MS
      tick([r], TICK_MS, now, finishM)
      if (r.boostUntilMs > prevBoostUntil) padFires++
      if (r.knockdownUntilMs > prevKnockUntil) hurdleFires++
      prevBoostUntil = r.boostUntilMs
      prevKnockUntil = r.knockdownUntilMs
    }
    return { padFires, hurdleFires }
  }

  it('1-lap race fires each pad and hurdle exactly once', () => {
    const { padFires, hurdleFires } = countFeatureFires(TRACK_M, TRACK_M - 1)
    expect(padFires).toBe(BOOST_PAD_FRACTIONS.length)
    expect(hurdleFires).toBe(HURDLE_FRACTIONS.length)
  })

  it('2-lap race fires each pad and hurdle exactly twice (once per lap)', () => {
    const { padFires, hurdleFires } = countFeatureFires(TWO_LAP_M, TWO_LAP_M - 1)
    expect(padFires).toBe(BOOST_PAD_FRACTIONS.length * 2)
    expect(hurdleFires).toBe(HURDLE_FRACTIONS.length * 2)
  })

  it('a feature straddled by the start-line wrap still fires correctly', () => {
    // Place a pad at the last fraction near the loop end, then take a tick
    // that wraps across the start line. The wrap split must catch a pad
    // sitting just before the line on the outgoing lap.
    const padM = boostPadPositionsM()[BOOST_PAD_FRACTIONS.length - 1] // 0.75 * 100 = 75
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    // Sit just past the last pad on lap 1; cross it again on lap 2 after a
    // start-line wrap. Position just before the start line, step over it.
    r.positionM = LOOP_LENGTH_M - 0.05
    tick([r], TICK_MS, TICK_MS, TWO_LAP_M) // wraps to ~0.1 — no pad at 0
    expect(r.boostUntilMs).toBe(0)
    // Now advance to just before the 75 m pad on lap 2 and cross it.
    r.positionM = LOOP_LENGTH_M + padM - 0.01
    tick([r], TICK_MS, 2 * TICK_MS, TWO_LAP_M)
    expect(r.boostUntilMs).toBe(2 * TICK_MS + BOOST_DURATION_MS)
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

  it('hitting a hurdle knocks the racer down: velocity zeroed, window opened', () => {
    const r = racerJustBeforeHurdle()
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.velocityMps).toBe(0)
    expect(isKnockedDown(r, TICK_MS)).toBe(true)
    expect(r.knockdownUntilMs).toBe(TICK_MS + HURDLE_KNOCKDOWN_MS)
  })

  it('hitting forfeits a banked sprint window', () => {
    const r = racerJustBeforeHurdle()
    triggerSprintTap(r, 0)
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.sprintUntilMs).toBeLessThanOrEqual(TICK_MS)
  })

  it('a downed racer stays on the ground — sprint taps are refused', () => {
    const r = racerJustBeforeHurdle()
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    triggerSprintTap(r, TICK_MS)
    expect(r.sprintUntilMs).toBeLessThanOrEqual(TICK_MS)
    advance(r, TICK_MS, 8) // still inside HURDLE_KNOCKDOWN_MS
    expect(r.velocityMps).toBe(0)
  })

  it('a downed racer cannot jump', () => {
    const r = racerJustBeforeHurdle()
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    triggerJump(r, TICK_MS + TICK_MS)
    expect(r.jumpUntilMs).toBe(0)
  })

  it('a walking racer falls too — knockdown is felt at any speed', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = WALK_TARGET_MPS
    r.positionM = hurdlePositionsM(TRACK_M)[0] - 0.01
    tick([r], TICK_MS, TICK_MS, TRACK_M)
    expect(r.velocityMps).toBe(0)
    expect(isKnockedDown(r, TICK_MS)).toBe(true)
  })

  it('speed is rebuilt from rest after the get-up', () => {
    const r = racerJustBeforeHurdle()
    let now = TICK_MS
    tick([r], TICK_MS, now, TRACK_M)
    now = advance(r, now, Math.ceil(HURDLE_KNOCKDOWN_MS / TICK_MS))
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
    expect(isKnockedDown(r, TICK_MS)).toBe(false)
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
