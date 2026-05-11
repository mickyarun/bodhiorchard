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

/**
 * RacePhysics — pure race mechanics.
 *
 * No PlayCanvas imports, no framework dependencies. Pure plain-data so
 * Phase 2 can hoist into a shared package consumed by both the client
 * (local mode) and the Colyseus server (live mode).
 *
 * Mechanic:
 *   - Holding a "move" key sets `isMoving = true`.
 *   - Tapping the sprint key extends `sprintUntilMs` by SPRINT_TAP_DURATION_MS,
 *     capped at SPRINT_MAX_WINDOW_MS above now. The racer is "sprinting"
 *     while `nowMs < sprintUntilMs`.
 *   - Each tick velocity accelerates toward:
 *       RUN_TARGET_MPS   if isMoving && sprinting
 *       WALK_TARGET_MPS  if isMoving && !sprinting
 *       0                otherwise (decelerates toward rest)
 *
 * Integrates at the caller's dt so movement is frame-smooth.
 */

import {
  WALK_TARGET_MPS,
  RUN_TARGET_MPS,
  MOVE_ACCEL_MPSS,
  MOVE_DECEL_MPSS,
  SPRINT_TAP_DURATION_MS,
  SPRINT_MAX_WINDOW_MS,
  V_MAX_MPS,
  TRACK_LENGTH_M,
} from './RaceConstants'
import type { Placing } from './types'

/**
 * Mutable state for one racer. Constructed once per round and mutated in
 * place.
 */
export interface Racer {
  readonly id: string
  positionM: number
  velocityMps: number
  finished: boolean
  /** ms since race start when the racer first crossed the finish line. 0 if not finished. */
  finishTimeMs: number
  /** True while the player is holding their move key. */
  isMoving: boolean
  /**
   * Round-ms at which the current sprint window ends. The racer is
   * sprinting iff nowMs < sprintUntilMs. 0 = not sprinting.
   */
  sprintUntilMs: number
}

export function makeRacer(id: string): Racer {
  return {
    id,
    positionM: 0,
    velocityMps: 0,
    finished: false,
    finishTimeMs: 0,
    isMoving: false,
    sprintUntilMs: 0,
  }
}

/** Update the move-key hold state. No-op for finished racers. */
export function setMoving(racer: Racer, isMoving: boolean): void {
  if (racer.finished) return
  racer.isMoving = isMoving
}

/**
 * Register a sprint-key tap. Extends the sprint window by
 * SPRINT_TAP_DURATION_MS but never past SPRINT_MAX_WINDOW_MS above now.
 */
export function triggerSprintTap(racer: Racer, nowMs: number): void {
  if (racer.finished) return
  const currentEnd = Math.max(nowMs, racer.sprintUntilMs)
  const newEnd = currentEnd + SPRINT_TAP_DURATION_MS
  const hardCap = nowMs + SPRINT_MAX_WINDOW_MS
  racer.sprintUntilMs = Math.min(newEnd, hardCap)
}

/**
 * Advance one physics step. Integrates velocity + position using the
 * caller-supplied dt (ms). Marks `finished` the first step a racer reaches
 * TRACK_LENGTH_M.
 */
export function tick(
  racers: Racer[],
  dtMs: number,
  nowMs: number,
  trackLengthM: number = TRACK_LENGTH_M,
): void {
  const dtSec = dtMs / 1000
  if (dtSec <= 0) return

  for (let i = 0; i < racers.length; i++) {
    const r = racers[i]
    if (r.finished) continue

    const sprinting = nowMs < r.sprintUntilMs
    stepVelocity(r, sprinting, dtSec)
    r.positionM += r.velocityMps * dtSec

    if (r.positionM >= trackLengthM) {
      r.finished = true
      r.finishTimeMs = nowMs
    }
  }
}

/** Is this racer currently inside a sprint burst? */
export function isSprinting(racer: Racer, nowMs: number): boolean {
  return nowMs < racer.sprintUntilMs
}

function stepVelocity(racer: Racer, sprinting: boolean, dtSec: number): void {
  let target: number
  let accel: number

  if (racer.isMoving) {
    target = sprinting ? RUN_TARGET_MPS : WALK_TARGET_MPS
    accel = MOVE_ACCEL_MPSS
  } else {
    target = 0
    accel = MOVE_DECEL_MPSS
  }

  const v = racer.velocityMps
  const deltaV = accel * dtSec
  if (v < target) {
    racer.velocityMps = Math.min(target, v + deltaV)
  } else if (v > target) {
    racer.velocityMps = Math.max(target, v - deltaV)
  }

  if (racer.velocityMps > V_MAX_MPS) racer.velocityMps = V_MAX_MPS
}

/**
 * Rank racers into finish places:
 *   1. Finishers first, ascending finishTimeMs.
 *   2. Same-tick tie: further post-tick positionM wins.
 *   3. Exact float tie: ascending racer id.
 *   4. DNFs after finishers, descending distance. Ties: ascending id.
 */
export function checkFinish(racers: readonly Racer[], timeoutFired: boolean): Placing[] {
  const sorted = racers.slice().sort((a, b) => {
    if (a.finished !== b.finished) return a.finished ? -1 : 1

    if (a.finished && b.finished) {
      if (a.finishTimeMs !== b.finishTimeMs) return a.finishTimeMs - b.finishTimeMs
      if (a.positionM !== b.positionM) return b.positionM - a.positionM
      return a.id.localeCompare(b.id)
    }

    if (a.positionM !== b.positionM) return b.positionM - a.positionM
    return a.id.localeCompare(b.id)
  })

  void timeoutFired
  return sorted.map((r, idx) => ({
    racerId: r.id,
    place: idx + 1,
    finished: r.finished,
    finishTimeMs: r.finished ? r.finishTimeMs : 0,
    distanceM: r.positionM,
  }))
}
