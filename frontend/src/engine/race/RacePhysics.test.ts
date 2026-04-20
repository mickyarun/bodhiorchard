// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { describe, it, expect } from 'vitest'
import {
  makeRacer,
  tick,
  setMoving,
  triggerSprintTap,
  isSprinting,
  checkFinish,
  type Racer,
} from '@shared/race/RacePhysics'
import {
  WALK_TARGET_MPS,
  RUN_TARGET_MPS,
  MOVE_ACCEL_MPSS,
  SPRINT_TAP_DURATION_MS,
  SPRINT_MAX_WINDOW_MS,
  TRACK_LENGTH_M,
} from '@shared/race/RaceConstants'

const FRAME_MS = 16  // ~60 fps

describe('RacePhysics.setMoving + tick — walk mode', () => {
  it('accelerates toward WALK_TARGET_MPS while moving without sprint', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    tick([r], FRAME_MS, FRAME_MS)
    expect(r.velocityMps).toBeCloseTo(MOVE_ACCEL_MPSS * (FRAME_MS / 1000), 5)
  })

  it('settles at WALK_TARGET_MPS after sustained walking', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    for (let t = 0; t < 120; t++) tick([r], FRAME_MS, (t + 1) * FRAME_MS)
    expect(r.velocityMps).toBeCloseTo(WALK_TARGET_MPS, 3)
  })

  it('decelerates to 0 when move released', () => {
    const r = makeRacer('a')
    r.velocityMps = WALK_TARGET_MPS
    setMoving(r, false)
    for (let t = 0; t < 120; t++) tick([r], FRAME_MS, (t + 1) * FRAME_MS)
    expect(r.velocityMps).toBe(0)
  })

  it('setMoving is a no-op for finished racers', () => {
    const r = makeRacer('a')
    r.finished = true
    setMoving(r, true)
    expect(r.isMoving).toBe(false)
  })
})

describe('RacePhysics.triggerSprintTap', () => {
  it('one tap gives SPRINT_TAP_DURATION_MS of sprint from now', () => {
    const r = makeRacer('a')
    triggerSprintTap(r, 0)
    expect(isSprinting(r, 0)).toBe(true)
    expect(isSprinting(r, SPRINT_TAP_DURATION_MS - 1)).toBe(true)
    expect(isSprinting(r, SPRINT_TAP_DURATION_MS)).toBe(false)
  })

  it('tapping while still sprinting extends the window (capped at SPRINT_MAX_WINDOW_MS)', () => {
    const r = makeRacer('a')
    triggerSprintTap(r, 0)
    triggerSprintTap(r, 50)
    triggerSprintTap(r, 100)
    // Three taps: 250 + 250 + 250 = 750 total, but capped at SPRINT_MAX_WINDOW_MS
    // above the latest `now` (100). So end is at most 100 + 600 = 700.
    expect(r.sprintUntilMs).toBeLessThanOrEqual(100 + SPRINT_MAX_WINDOW_MS)
  })

  it('tapping after the window ended starts a fresh window', () => {
    const r = makeRacer('a')
    triggerSprintTap(r, 0)
    // Wait past the first window.
    const laterMs = SPRINT_TAP_DURATION_MS + 100
    expect(isSprinting(r, laterMs)).toBe(false)
    triggerSprintTap(r, laterMs)
    expect(isSprinting(r, laterMs)).toBe(true)
    expect(isSprinting(r, laterMs + SPRINT_TAP_DURATION_MS - 1)).toBe(true)
  })

  it('lets a sustained tap cadence keep velocity at RUN_TARGET_MPS', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    // Tap roughly every 200ms for 3 seconds. Each tap gives 250ms of
    // sprint, so the window always overlaps with the next tap.
    let nextTapAt = 0
    for (let t = 0; t < 3000; t += FRAME_MS) {
      if (t >= nextTapAt) {
        triggerSprintTap(r, t)
        nextTapAt = t + 200
      }
      tick([r], FRAME_MS, t + FRAME_MS)
    }
    expect(r.velocityMps).toBeCloseTo(RUN_TARGET_MPS, 3)
  })

  it('lapsed tap cadence drops velocity back toward WALK_TARGET_MPS', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    triggerSprintTap(r, 0)
    // Run frames past the sprint window without further taps.
    for (let t = 0; t < 2000; t += FRAME_MS) tick([r], FRAME_MS, t + FRAME_MS)
    expect(r.velocityMps).toBeCloseTo(WALK_TARGET_MPS, 3)
  })

  it('triggerSprintTap is a no-op for finished racers', () => {
    const r = makeRacer('a')
    r.finished = true
    triggerSprintTap(r, 0)
    expect(r.sprintUntilMs).toBe(0)
  })
})

describe('RacePhysics.tick — integration + finish detection', () => {
  it('integrates position using the caller-supplied dt', () => {
    const r = makeRacer('a')
    r.velocityMps = 5
    setMoving(r, true)
    triggerSprintTap(r, 0)
    tick([r], FRAME_MS, FRAME_MS)
    expect(r.positionM).toBeGreaterThan(0.07)
    expect(r.positionM).toBeLessThan(0.12)
  })

  it('marks a racer finished the first frame they cross TRACK_LENGTH_M', () => {
    const r = makeRacer('a')
    r.positionM = TRACK_LENGTH_M - 0.01
    r.velocityMps = 5
    setMoving(r, true)
    tick([r], FRAME_MS, FRAME_MS)
    expect(r.finished).toBe(true)
    expect(r.finishTimeMs).toBe(FRAME_MS)
  })

  it('skips already-finished racers', () => {
    const r = makeRacer('a')
    r.finished = true
    r.positionM = TRACK_LENGTH_M + 2
    r.velocityMps = 5
    const frozenPos = r.positionM
    const frozenVel = r.velocityMps
    tick([r], FRAME_MS, FRAME_MS)
    expect(r.positionM).toBe(frozenPos)
    expect(r.velocityMps).toBe(frozenVel)
  })

  it('ignores zero / negative dt', () => {
    const r = makeRacer('a')
    setMoving(r, true)
    r.velocityMps = 3
    const posBefore = r.positionM
    tick([r], 0, 0)
    tick([r], -10, 0)
    expect(r.positionM).toBe(posBefore)
  })
})

describe('RacePhysics.checkFinish', () => {
  function racerAt(id: string, positionM: number, finished = false, finishTimeMs = 0): Racer {
    const r = makeRacer(id)
    r.positionM = positionM
    r.finished = finished
    r.finishTimeMs = finishTimeMs
    return r
  }

  it('ranks finishers before DNFs, ordered by finishTimeMs ascending', () => {
    const racers = [
      racerAt('c', 60, true, 3000),
      racerAt('a', 60, true, 2500),
      racerAt('b', 45, false),
      racerAt('d', 60, true, 2750),
    ]
    const places = checkFinish(racers, true)
    expect(places.map(p => p.racerId)).toEqual(['a', 'd', 'c', 'b'])
  })

  it('tie-breaks same-tick finish by post-tick distance', () => {
    const racers = [
      racerAt('a', 60.10, true, 1000),
      racerAt('b', 60.05, true, 1000),
    ]
    const places = checkFinish(racers, false)
    expect(places[0].racerId).toBe('a')
    expect(places[1].racerId).toBe('b')
  })

  it('tie-breaks exact float tie by ascending id', () => {
    const racers = [
      racerAt('zulu',  60.1, true, 1000),
      racerAt('alpha', 60.1, true, 1000),
    ]
    const places = checkFinish(racers, false)
    expect(places[0].racerId).toBe('alpha')
    expect(places[1].racerId).toBe('zulu')
  })

  it('ranks DNFs by descending distance, ties by id', () => {
    const racers = [
      racerAt('a', 45),
      racerAt('b', 55),
      racerAt('c', 55),
    ]
    const places = checkFinish(racers, true)
    expect(places.map(p => p.racerId)).toEqual(['b', 'c', 'a'])
  })

  it('single-finisher race marks others in distance order', () => {
    const racers = [
      racerAt('a', 60, true, 10000),
      racerAt('b', 32),
      racerAt('c', 44),
      racerAt('d', 18),
    ]
    const places = checkFinish(racers, true)
    expect(places.map(p => p.racerId)).toEqual(['a', 'c', 'b', 'd'])
  })
})
